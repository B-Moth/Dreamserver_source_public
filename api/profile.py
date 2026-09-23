"""User profile persistence and prompt context."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from api.config import USER_PROFILE_FILE, load_config


def profile_path() -> Path:
    try:
        config = load_config()
        custom = str(config.get("profile_file") or "").strip()
        if custom:
            path = Path(custom)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return USER_PROFILE_FILE


def empty_user_profile() -> dict:
    return {
        "first_name": "",
        "last_name": "",
        "pronouns": "",
        "birthday": "",
        "pet": "",
        "closest_relative": "",
        "closest_relative_status": "",
        "other_notes": "",
        "updated_at": None,
    }


def sanitize_profile_value(value, limit: int = 280) -> str:
    return str(value or "").strip()[:limit]


def sanitize_user_profile(payload: dict | None) -> dict:
    data = payload or {}
    clean = empty_user_profile()
    clean["first_name"] = sanitize_profile_value(data.get("first_name"), 80)
    clean["last_name"] = sanitize_profile_value(data.get("last_name"), 80)
    clean["pronouns"] = sanitize_profile_value(data.get("pronouns"), 120)
    clean["birthday"] = sanitize_profile_value(data.get("birthday"), 40)
    clean["pet"] = sanitize_profile_value(data.get("pet"), 160)
    clean["closest_relative"] = sanitize_profile_value(
        data.get("closest_relative"), 160
    )
    clean["closest_relative_status"] = sanitize_profile_value(
        data.get("closest_relative_status"), 220
    )
    clean["other_notes"] = sanitize_profile_value(data.get("other_notes"), 500)
    clean["updated_at"] = datetime.now().isoformat()
    return clean


def load_user_profile() -> dict:
    path = profile_path()
    if not path.exists():
        return empty_user_profile()
    try:
        with open(path) as profile_file:
            data = json.load(profile_file)
        if not isinstance(data, dict):
            return empty_user_profile()
        merged = empty_user_profile()
        for key in merged.keys():
            if key == "updated_at":
                merged[key] = data.get(key)
            else:
                merged[key] = sanitize_profile_value(
                    data.get(key), 500 if key == "other_notes" else 280
                )
        return merged
    except Exception:
        return empty_user_profile()


def save_user_profile(profile: dict) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as profile_file:
        json.dump(profile, profile_file, ensure_ascii=False, indent=2)


def user_profile_for_prompt() -> str:
    profile = load_user_profile()
    fields = [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("pronouns", "Pronouns"),
        ("birthday", "Birthday"),
        ("pet", "Pet"),
        ("closest_relative", "Closest relative"),
        ("closest_relative_status", "Relative status"),
        ("other_notes", "Other relevant notes"),
    ]
    lines = []
    for key, label in fields:
        value = str(profile.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def user_addressing_instruction() -> str:
    profile = load_user_profile()
    first_name = str(profile.get("first_name") or "").strip()
    pronouns = str(profile.get("pronouns") or "").strip()

    if not first_name and not pronouns:
        return "Adresse-toi directement a l'utilisateur en deuxieme personne (tu/ton/tes)."

    lines = [
        "Consignes de personnalisation prioritaires:",
        "- Ecris uniquement en francais.",
        "- Adresse-toi directement a l'utilisateur en deuxieme personne (tu/ton/tes).",
    ]
    if first_name:
        lines.append(
            f'- Utilise le prenom "{first_name}" quand tu t\'adresses a la personne.'
        )
    if pronouns:
        normalized = pronouns.lower().replace("·", "").replace(" ", "")
        lines.append(f'- Pronoms preferes: "{pronouns}".')
        lines.append(
            "- N'invente pas et ne traduis pas les pronoms "
            '(interdit: "they/them" ou "Nom/Them" si ce n\'est pas fourni).'
        )
        if "iel" in normalized:
            lines.append(
                '- Si une phrase impose la troisieme personne, utilise explicitement "iel" '
                "et garde une formulation inclusive."
            )
        else:
            lines.append(
                "- Si une phrase impose la troisieme personne, reprends exactement les pronoms fournis."
            )
    lines.append("- Ne commente pas ces consignes dans la reponse.")
    return "\n".join(lines)


def user_profile_signature() -> str:
    profile = load_user_profile()
    payload = {
        key: profile.get(key)
        for key in (
            "first_name",
            "last_name",
            "pronouns",
            "birthday",
            "pet",
            "closest_relative",
            "closest_relative_status",
            "other_notes",
        )
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()