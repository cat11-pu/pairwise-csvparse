"""CSV parsing kernel built on the standard library only.

The kernel turns a document into records and turns records back into a
document without losing a value on the way:

* A field is quoted when its first character is the quote character; a quote
  inside an unquoted field is an ordinary character.
* Inside a quoted field a doubled quote stands for one quote, and the line
  breaks are field data rather than record separators.
* Outside quotes a record ends at a newline, at a carriage return or at a
  CRLF pair.
* A byte order mark in front of the first field is not part of the value.
* Every record of a document holds the same number of fields: a strict reader
  reports the odd ones, a relaxed reader pads the short ones with empty
  fields and keeps the long ones as they are.

Nothing here touches the disk, the network, the clock or the random number
generator: the same text always yields the same records.
"""

#: Character that separates two fields of a record.
DELIMITER = ","

#: Character that wraps a field which needs protection.
QUOTE = '"'

#: Character this kernel writes at the end of every record.
TERMINATOR = "\n"

#: Mark a text editor may leave in front of a document saved as UTF-8.
BOM = "\ufeff"

#: States a field walks through while a document is scanned.
_FIELD_START = 0
_FIELD_PLAIN = 1
_FIELD_QUOTED = 2
_FIELD_CLOSED = 3


class CSVError(Exception):
    """Raised when a document cannot be read as CSV.

    ``line`` is the one based number of the line the offending record starts
    on, so a caller can point the reader at the place in the file.
    """

    def __init__(self, message, line=0):
        super().__init__(message)
        self.message = message
        self.line = line


class Record:
    """One record of a document: its fields and the line it starts on."""

    __slots__ = ("fields", "line")

    def __init__(self, fields, line):
        self.fields = list(fields)
        self.line = line

    def __len__(self):
        return len(self.fields)

    def __iter__(self):
        return iter(self.fields)

    def __getitem__(self, index):
        return self.fields[index]

    def __eq__(self, other):
        if isinstance(other, Record):
            return self.fields == other.fields and self.line == other.line
        return NotImplemented

    def __hash__(self):
        return hash((tuple(self.fields), self.line))

    def __repr__(self):
        return "Record(fields=%r, line=%r)" % (self.fields, self.line)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _strip_bom(text):
    """Return text without the mark that may sit in front of the first field."""
    if text.startswith("\xef\xbb\xbf"):
        return text[1:]
    return text


def _scan(text, delimiter, quotechar):
    """Split text into (fields, line) pairs, one pair per record.

    The line of a pair is the line its record starts on, counted from one.
    """
    records = []
    row = []
    buf = []
    state = _FIELD_START
    line = 1
    row_line = 1
    index = 0
    size = len(text)

    while index < size:
        char = text[index]

        if char == "\n":
            # A record ends here and the next one starts on the next line.
            row.append("".join(buf))
            records.append((row, row_line))
            row = []
            buf = []
            line += 1
            row_line = line
            state = _FIELD_START
            index += 1
            continue

        if state == _FIELD_QUOTED:
            if char == quotechar:
                if index + 1 < size and text[index + 1] == quotechar:
                    buf.append(char)
                    buf.append(char)
                    index += 2
                    continue
                state = _FIELD_CLOSED
                index += 1
                continue
            if char == "\n" or char == "\r":
                if char == "\r" and index + 1 < size and text[index + 1] == "\n":
                    buf.append("\r\n")
                    index += 2
                else:
                    buf.append(char)
                    index += 1
                continue
            buf.append(char)
            index += 1
            continue

        if char == delimiter:
            row.append("".join(buf))
            buf = []
            state = _FIELD_START
            index += 1
            continue

        if state == _FIELD_START and char == quotechar:
            state = _FIELD_QUOTED
            index += 1
            continue

        if state == _FIELD_CLOSED:
            raise CSVError(
                "unexpected character %r after a closing quote" % (char,), line
            )

        buf.append(char)
        state = _FIELD_PLAIN
        index += 1

    # The last field of the document ends with the document itself.
    if row or buf or state != _FIELD_START:
        row.append("".join(buf))
        records.append((row, row_line))
    return records


def parse_records(text, delimiter=DELIMITER, quotechar=QUOTE, strict=True):
    """Read a whole document, returning one Record per line of it.

    The first record of a document decides how wide its records are.  A
    strict reader raises CSVError on a record of a different width; a relaxed
    reader pads the short records with empty fields and keeps the long ones.
    """
    if not isinstance(text, str):
        raise TypeError("a document must be text, not %s" % type(text).__name__)
    records = [
        Record(fields, line)
        for fields, line in _scan(_strip_bom(text), delimiter, quotechar)
    ]
    if not records:
        return records
    width = len(records[0].fields)
    for record in records:
        if len(record.fields) >= width:
            continue
        if strict:
            raise CSVError(
                "the record on line %d holds %d fields, but the document "
                "starts with %d" % (record.line, len(record.fields), width),
                record.line,
            )
        while len(record.fields) < width:
            record.fields.append("")
    return records


def parse_csv(text, delimiter=DELIMITER, quotechar=QUOTE, strict=True):
    """Read a whole document, returning a list of field lists."""
    return [
        record.fields
        for record in parse_records(text, delimiter=delimiter, quotechar=quotechar, strict=strict)
    ]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def needs_quotes(field, delimiter=DELIMITER, quotechar=QUOTE):
    """Say whether a field has to travel between quotes.

    A field is wrapped when writing it bare would hand the reader a different
    document: when it holds the delimiter or the quote character, or when it
    holds a line break.
    """
    if field == "":
        return False
    for mark in (delimiter, quotechar):
        if mark in field:
            return True
    return False


def _write_field(field, delimiter, quotechar):
    """Write one field, wrapped between quotes only where that is needed."""
    if not isinstance(field, str):
        raise TypeError("a field must be text, not %s" % type(field).__name__)
    if needs_quotes(field, delimiter, quotechar):
        return quotechar + field.replace(quotechar, quotechar * 2) + quotechar
    return field


def encode_rows(rows, delimiter=DELIMITER, quotechar=QUOTE, terminator=TERMINATOR):
    """Write records back as a document the reader reads as those records.

    Every record needs at least one field.  A record that holds a single
    empty field is written between quotes, so that it does not come back as
    an empty line.
    """
    out = []
    for row in rows:
        fields = list(row)
        for field in fields:
            if not isinstance(field, str):
                raise TypeError("a field must be text, not %s" % type(field).__name__)
        if len(fields) == 1 and fields[0] == "":
            out.append(quotechar * 2)
        else:
            out.append(
                delimiter.join(
                    _write_field(field, delimiter, quotechar) for field in fields
                )
            )
        out.append(terminator)
    return "".join(out)
