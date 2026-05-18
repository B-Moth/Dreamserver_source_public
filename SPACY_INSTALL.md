spaCy French model (optional)

For improved Dream Map accuracy install spaCy and a French model.

Recommended (small model):

```bash
pip install spacy
python -m spacy download fr_core_news_sm
```

If you prefer a better model (more accurate but larger):

```bash
python -m spacy download fr_core_news_md
```

Restart the server after installation so the new model is loaded.
