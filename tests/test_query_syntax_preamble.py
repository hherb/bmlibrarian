"""
Tests for strip_preamble.

Generation ceilings in the query paths were raised (rephrasing 50 -> 800,
query generation 100 -> 800) so reasoning models could think before
answering. Those tight ceilings had been doing unintended double duty: a
chatty model physically could not fit "Here is the query:" plus an answer
into 50 tokens, so the parsers downstream never had to cope with a
preamble. At 800 they do, and the checks they had ("longer than five
characters", "strip markdown fences") would pass a preamble straight
through into a PostgreSQL to_tsquery string or a semantic search.
"""

import pytest

from bmlibrarian.agents.utils.query_syntax import strip_preamble


class TestPreambleIsDropped:
    """Cases where a lead-in precedes the answer."""

    def test_colon_terminated_lead_in_is_dropped(self) -> None:
        """The canonical chatty-model shape."""
        assert strip_preamble(
            "Here is the query:\n\nexercise & cardiac"
        ) == "exercise & cardiac"

    def test_blank_lines_between_lead_in_and_answer_are_ignored(self) -> None:
        """Spacing between the two does not matter."""
        assert strip_preamble(
            "Sure! The rewritten query:\n\n\n   statins | cholesterol   "
        ) == "statins | cholesterol"

    def test_everything_after_the_lead_in_is_kept(self) -> None:
        """
        Only the lead-in goes; the remainder is returned verbatim.

        Returning just the next line would truncate a multi-line answer
        and would break a fenced code block, which the query-generation
        path strips separately afterwards.
        """
        assert strip_preamble(
            "Here is the query:\n```\nexercise & cardiac\n```"
        ) == "```\nexercise & cardiac\n```"

    def test_multi_line_answer_survives_the_lead_in(self) -> None:
        """A wrapped answer is not cut down to its first line."""
        assert strip_preamble(
            "Alternative query:\nexercise & cardiac\n| fitness"
        ) == "exercise & cardiac\n| fitness"


class TestTextWithoutPreambleIsUnchanged:
    """The helper must be safe to apply unconditionally."""

    def test_bare_answer_passes_through(self) -> None:
        """A one-line answer is returned as-is."""
        assert strip_preamble("exercise & cardiac") == "exercise & cardiac"

    def test_surrounding_whitespace_is_stripped(self) -> None:
        """Leading and trailing whitespace is removed."""
        assert strip_preamble("  exercise & cardiac  ") == "exercise & cardiac"

    def test_a_single_line_containing_a_colon_is_not_treated_as_a_lead_in(
        self,
    ) -> None:
        """With nothing following it, a colon-ending line is the answer."""
        assert strip_preamble("ratio:") == "ratio:"

    def test_mid_sentence_colon_does_not_trigger_stripping(self) -> None:
        """Only a line *ending* in a colon counts as a lead-in."""
        assert strip_preamble(
            "ratio: 3:1 in favour\nsecond line"
        ) == "ratio: 3:1 in favour\nsecond line"

    def test_multi_line_answer_without_lead_in_is_untouched(self) -> None:
        """A non-preamble first line means nothing is dropped."""
        assert strip_preamble(
            "exercise & cardiac\nmore text"
        ) == "exercise & cardiac\nmore text"

    def test_fenced_block_without_lead_in_is_untouched(self) -> None:
        """A fence opener is not a lead-in, so the block survives."""
        assert strip_preamble(
            "```\nexercise & cardiac\n```"
        ) == "```\nexercise & cardiac\n```"


class TestDegenerateInput:
    """Empty and whitespace-only completions."""

    @pytest.mark.parametrize("text", ["", "   ", "\n\n", "  \n \n "])
    def test_empty_input_yields_empty_string(self, text: str) -> None:
        """Nothing in, empty string out — never an IndexError."""
        assert strip_preamble(text) == ""


class TestSanitizeQueryComposition:
    """
    Cover strip_preamble composed with markdown-fence removal.

    These are separate cleanup steps applied in sequence, and the order
    matters. An earlier version of strip_preamble returned only the line
    after the lead-in, which reduced a fenced query to its opening ```
    and made the fence-stripping that follows produce an empty query.
    """

    @staticmethod
    def _sanitize(raw: str) -> str:
        """Run the generator's sanitiser without constructing one."""
        from bmlibrarian.agents.query_generation.generator import (
            MultiModelQueryGenerator,
        )

        generator = MultiModelQueryGenerator.__new__(MultiModelQueryGenerator)
        return generator._sanitize_query(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "exercise & cardiac",
            "```\nexercise & cardiac\n```",
            "```sql\nexercise & cardiac\n```",
            "Here is the query:\n\nexercise & cardiac",
            "Here is the query:\n```\nexercise & cardiac\n```",
        ],
    )
    def test_every_wrapper_reduces_to_the_bare_query(self, raw: str) -> None:
        """Preamble and fences, alone or combined, are both removed."""
        assert self._sanitize(raw) == "exercise & cardiac"
