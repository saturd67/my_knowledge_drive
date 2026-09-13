"""Counts the tokens the embedding model sees, so a file can be fitted to its window.

Uses the model's own tokenizer when it can be loaded - it is already in the
Hugging Face cache once the embedder has run - and falls back to an estimate
when it cannot, so a missing download never stops a conversion.
"""

import logging

logger = logging.getLogger(__name__)


class TokenCounter:

    #: Characters per token for the estimate. English averages about four per
    #: WordPiece token; three over-counts on purpose, so an estimated file
    #: lands inside the real window rather than just past it.
    ESTIMATED_CHARACTERS_PER_TOKEN = 3

    def __init__(self, model_name):
        self.model_name = model_name
        self._tokenizer = None
        self._is_loaded = False

    def count(self, text):
        """Tokens in `text`, not counting the [CLS] and [SEP] the model adds."""
        tokenizer = self._load()
        if tokenizer is None:
            return sum(
                -(-len(word) // TokenCounter.ESTIMATED_CHARACTERS_PER_TOKEN)
                for word in text.split()
            )
        return len(tokenizer.tokenize(text))

    def _load(self):
        """The tokenizer, loaded on first use - or None, once, if it cannot be."""
        if self._is_loaded:
            return self._tokenizer
        self._is_loaded = True

        # Settings hold the short sentence-transformers name; the hub wants the
        # organisation in front of it.
        repository_id = self.model_name if "/" in self.model_name else f"sentence-transformers/{self.model_name}"
        try:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(repository_id)
        except Exception as error:
            logger.warning(f"Could not load the {repository_id} tokenizer, estimating tokens instead - {error}")
            self._tokenizer = None
        return self._tokenizer
