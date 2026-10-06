"""Behaviour tests for the CSV parsing kernel.

The tests only describe what a caller of the kernel is allowed to observe:
the records that come out of a document, the lines those records report, the
errors a broken document raises, and the text the writer produces.  Run them
from the project root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csvparse.core as csvparse


class ReadingTests(unittest.TestCase):
    """Documents a caller hands to the reader."""

    def test_plain_records_and_empty_fields(self):
        text = "id,name\n1,amy\n2,bob\n"
        self.assertEqual(
            csvparse.parse_csv(text),
            [["id", "name"], ["1", "amy"], ["2", "bob"]],
        )
        self.assertEqual(csvparse.parse_csv(""), [])
        self.assertEqual(csvparse.parse_csv("a,b"), [["a", "b"]])
        self.assertEqual(csvparse.parse_csv("a,,b,\n"), [["a", "", "b", ""]])
        self.assertEqual(csvparse.parse_csv(",\n"), [["", ""]])
        self.assertEqual(csvparse.parse_csv('""\n'), [[""]])

    def test_a_doubled_quote_inside_a_field_is_one_quote(self):
        text = 'a,"he said ""hi""",b\n'
        self.assertEqual(
            csvparse.parse_csv(text),
            [["a", 'he said "hi"', "b"]],
        )
        self.assertEqual(csvparse.parse_csv('a,"""",b\n'), [["a", '"', "b"]])
        self.assertEqual(
            csvparse.parse_csv('a,"a""""b",c\n'),
            [["a", 'a""b', "c"]],
        )

    def test_a_quoted_field_keeps_its_line_breaks(self):
        text = 'k,v\n"a\nb",c\nd,e\n'
        self.assertEqual(
            csvparse.parse_csv(text, strict=False),
            [["k", "v"], ["a\nb", "c"], ["d", "e"]],
        )
        records = csvparse.parse_records(text, strict=False)
        self.assertEqual([record.line for record in records], [1, 2, 4])
        self.assertEqual(records[1].fields[0], "a\nb")

    def test_line_endings_are_interchangeable(self):
        expected = [["a", "b"], ["c", "d"]]
        self.assertEqual(csvparse.parse_csv("a,b\nc,d\n"), expected)
        self.assertEqual(
            csvparse.parse_csv("a,b\r\nc,d\r\n", strict=False),
            expected,
        )
        self.assertEqual(
            csvparse.parse_csv("a,b\rc,d\r", strict=False),
            expected,
        )

    def test_a_byte_order_mark_is_not_part_of_the_first_field(self):
        self.assertEqual(
            csvparse.parse_csv("\ufeffid,name\n"),
            [["id", "name"]],
        )
        self.assertEqual(
            csvparse.parse_csv('\ufeff"id",name\n'),
            [["id", "name"]],
        )
        self.assertEqual(
            csvparse.parse_csv("id\ufeffx,name\n"),
            [["id\ufeffx", "name"]],
        )

    def test_an_unclosed_quote_is_reported_with_its_line(self):
        text = 'k,v\n"a\nb",c\n"oops,1\n'
        with self.assertRaises(csvparse.CSVError) as caught:
            csvparse.parse_csv(text)
        self.assertEqual(caught.exception.line, 4)
        self.assertRaises(csvparse.CSVError, csvparse.parse_csv, 'a,"oops')

    def test_records_of_the_wrong_width_are_not_accepted(self):
        text = "a,b\nc,d,e\n"
        with self.assertRaises(csvparse.CSVError) as caught:
            csvparse.parse_csv(text)
        self.assertEqual(caught.exception.line, 2)
        self.assertEqual(
            csvparse.parse_csv("a,b,c\nx\n", strict=False),
            [["a", "b", "c"], ["x", "", ""]],
        )
        self.assertEqual(
            csvparse.parse_csv("a,b\nc,d,e\n", strict=False),
            [["a", "b"], ["c", "d", "e"]],
        )

    def test_records_keep_their_fields_and_start_line(self):
        records = csvparse.parse_records('a,b\n"c,d",e\n')
        self.assertEqual([record.fields for record in records], [["a", "b"], ["c,d", "e"]])
        self.assertEqual([record.line for record in records], [1, 2])
        self.assertEqual(list(records[1]), ["c,d", "e"])
        self.assertEqual(len(records[0]), 2)
        self.assertEqual(records[1][0], "c,d")
        self.assertEqual(records[0], csvparse.Record(["a", "b"], 1))


class WritingTests(unittest.TestCase):
    """Records a caller hands to the writer."""

    def test_the_writer_quotes_only_where_it_must(self):
        self.assertEqual(
            csvparse.encode_rows([["id", "name"], ["1", "amy"]]),
            "id,name\n1,amy\n",
        )
        self.assertEqual(csvparse.encode_rows([["a,b", "c"]]), '"a,b",c\n')
        self.assertEqual(
            csvparse.encode_rows([['say "hi"', "x"]]),
            '"say ""hi""",x\n',
        )
        self.assertEqual(csvparse.encode_rows([[""]]), '""\n')
        self.assertEqual(
            csvparse.encode_rows([[" lead", "trail "]]),
            " lead,trail \n",
        )

    def test_a_field_with_a_line_break_survives_the_round_trip(self):
        self.assertEqual(csvparse.encode_rows([["a\nb", "c"]]), '"a\nb",c\n')
        self.assertEqual(csvparse.encode_rows([["a\rb"]]), '"a\rb"\n')
        rows = [
            ["id", "note"],
            ["1", 'he said "hi", loudly'],
            ["2", "first\nsecond"],
            ["3", ""],
        ]
        text = csvparse.encode_rows(rows)
        self.assertEqual(
            text,
            'id,note\n1,"he said ""hi"", loudly"\n2,"first\nsecond"\n3,\n',
        )
        self.assertEqual(csvparse.parse_csv(text), rows)


if __name__ == "__main__":
    unittest.main()
