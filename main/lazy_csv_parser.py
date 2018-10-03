from io import StringIO
from base64 import b64decode
from csv import DictReader, Sniffer
from typing import List, Generator, NewType, Dict

from main.csv_adapter import CsvAdapter
from main.csv_mapper import SomeModel
from main.infrastructure.either import Left, Right, Either
from main.infrastructure.message import Message, MessageCategory

File = NewType('File', object)


class LazyCsvParser:

    def __init__(self, adapter: CsvAdapter, fields: List[str]):
        if not fields:
            raise ValueError('Field names required.')

        self._adapter = adapter
        self._fields = fields

    def read_from_base64(self, content: str, ignore_headers=True) -> Generator[Either[Message, SomeModel], None, None]:
        b64_content = b64decode(content).decode("utf-8")

        some_file = StringIO(b64_content)

        yield from self._read_file_safe(some_file, ignore_headers)

    def read_from_file(self, filename: str, ignore_headers=True) -> Generator[Either[Message, SomeModel], None, None]:
        some_file = open(filename)

        yield from self._read_file_safe(some_file, ignore_headers)

    def _read_file_safe(self, some_file: File, ignore_headers: bool) -> Generator[Either[Message, SomeModel], None, None]:
        sniffer = Sniffer()
        try:
            with some_file as csv:
                dialect = sniffer.sniff(csv.read(1024))

                csv.seek(0)

                reader = DictReader(f=csv, fieldnames=self._fields, dialect=dialect)

                yield from self._read(reader, ignore_headers)
        except Exception as e:
            message = Message(category=MessageCategory.ERROR, key='import_csv_generic_error', args=[e])

            yield Left([message])

    def _read(self, reader: DictReader, ignore_headers: bool) -> Generator[Either[Message, SomeModel], None, None]:
        if ignore_headers:
            next(reader)

        for line_dict in reader:

            is_valid = yield from self._return_validation_of_fields_length_greater_or_equal_than_self_fields_and_if_all_fields_are_present_in_line_and_validate_all_inputs__Yield_left_messages_to_caller_if_any_validation_fails(
                reader, line_dict)

            if is_valid:
                try:
                    yield Right(self._adapter.to_model(line_dict))
                except Exception as e:
                    yield Left(e)
            else:
                break

    def _return_validation_of_fields_length_greater_or_equal_than_self_fields_and_if_all_fields_are_present_in_line_and_validate_all_inputs__Yield_left_messages_to_caller_if_any_validation_fails(
            self, reader, line_dict: Dict):
        fields = line_dict.keys()

        if len(fields) > len(self._fields):
            message = Message(category=MessageCategory.VALIDATION, key='import_csv_enough_fields', args=[reader.line_num, self._fields])

            yield Left([message])

            return False

        values = line_dict.values()

        if not all(values):
            missing_keys = [key for key, value in line_dict.items() if not value]

            message = Message(category=MessageCategory.VALIDATION, key='import_csv_missing_fields',
                              args=[reader.line_num, self._fields, missing_keys])

            yield Left([message])

            return False

        violations = self._adapter.validate(line_dict, line_number=reader.line_num)

        if violations:
            yield Left(violations)

            return False

        return True
