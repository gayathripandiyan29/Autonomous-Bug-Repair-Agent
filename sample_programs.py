"""
Curated Library of Buggy Sample Programs and Test Suites.
Demonstrates NameError, SyntaxError, IndexError, TypeError, KeyError, and Logic Bugs
for educational testing and agent benchmarking.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BuggySample:
    id: str
    title: str
    category: str
    description: str
    code: str
    traceback: str
    test_code: str
    expected_fix_summary: str


SAMPLE_PROGRAMS: Dict[str, BuggySample] = {
    "name_error": BuggySample(
        id="name_error",
        title="1. NameError (Typo in Variable Name)",
        category="NameError",
        description="A sales tax calculator references 'tax_rat' instead of the defined parameter 'tax_rate'.",
        code="""def calculate_total(subtotal, tax_rate):
    \"\"\"Calculates total amount including tax.\"\"\"
    tax_amount = subtotal * tax_rat
    total = subtotal + tax_amount
    return total
""",
        traceback="""Traceback (most recent call last):
  File "solution.py", line 3, in calculate_total
    tax_amount = subtotal * tax_rat
NameError: name 'tax_rat' is not defined. Did you mean: 'tax_rate'?
""",
        test_code="""import pytest
from solution import calculate_total

def test_calculate_total_standard():
    assert calculate_total(100.0, 0.05) == 105.0

def test_calculate_total_zero_tax():
    assert calculate_total(50.0, 0.0) == 50.0
""",
        expected_fix_summary="Replace the misspelled identifier 'tax_rat' with 'tax_rate' on line 3."
    ),

    "syntax_error": BuggySample(
        id="syntax_error",
        title="2. SyntaxError (Missing Colon on Function Def)",
        category="SyntaxError",
        description="A function definition is missing a terminating colon ':', causing compilation failure.",
        code="""def is_even(number)
    \"\"\"Returns True if number is even, False otherwise.\"\"\"
    return number % 2 == 0
""",
        traceback="""  File "solution.py", line 1
    def is_even(number)
                       ^
SyntaxError: expected ':'
""",
        test_code="""import pytest
from solution import is_even

def test_even_numbers():
    assert is_even(4) is True
    assert is_even(0) is True

def test_odd_numbers():
    assert is_even(7) is False
    assert is_even(-3) is False
""",
        expected_fix_summary="Add a colon ':' at the end of the 'def is_even(number)' statement."
    ),

    "index_error": BuggySample(
        id="index_error",
        title="3. IndexError (Off-by-One Array Access)",
        category="IndexError",
        description="An off-by-one indexing error where the last element is accessed via items[len(items)].",
        code="""def get_last_element(items):
    \"\"\"Returns the last element of a non-empty list.\"\"\"
    if not items:
        return None
    return items[len(items)]
""",
        traceback="""Traceback (most recent call last):
  File "solution.py", line 5, in get_last_element
    return items[len(items)]
IndexError: list index out of range
""",
        test_code="""import pytest
from solution import get_last_element

def test_get_last_numbers():
    assert get_last_element([10, 20, 30]) == 30

def test_get_last_single():
    assert get_last_element(["alpha"]) == "alpha"

def test_get_last_empty():
    assert get_last_element([]) is None
""",
        expected_fix_summary="Change indexing from items[len(items)] to items[-1] or items[len(items) - 1]."
    ),

    "logic_error": BuggySample(
        id="logic_error",
        title="4. Failing Unit Test (Logic Flaw in Discount Calculation)",
        category="LogicalError",
        description="Discount logic subtracts percentage directly (price - discount) rather than multiplying (price - price * discount).",
        code="""def apply_discount(price, discount):
    \"\"\"Applies a fractional discount (e.g., 0.15 for 15%) to an item's price.\"\"\"
    if discount < 0 or discount > 1:
        raise ValueError("Discount must be between 0 and 1.")
    return price - discount
""",
        traceback="""Traceback (most recent call last):
  File "test_solution.py", line 5, in test_apply_ten_percent_discount
    assert apply_discount(100.0, 0.10) == 90.0
AssertionError: assert 99.9 == 90.0
""",
        test_code="""import pytest
from solution import apply_discount

def test_apply_ten_percent_discount():
    assert apply_discount(100.0, 0.10) == 90.0

def test_apply_zero_discount():
    assert apply_discount(50.0, 0.0) == 50.0

def test_apply_fifty_percent():
    assert apply_discount(200.0, 0.50) == 100.0
""",
        expected_fix_summary="Compute discount amount as price * discount: return price - (price * discount)."
    ),

    "type_error": BuggySample(
        id="type_error",
        title="5. TypeError (Implicit String Concatenation with Int)",
        category="TypeError",
        description="Attempts to concatenate string with an integer without explicit type conversion.",
        code="""def format_user_badge(username, user_id):
    \"\"\"Creates a badge identifier string for a user.\"\"\"
    badge = "User #" + user_id
    return badge
""",
        traceback="""Traceback (most recent call last):
  File "solution.py", line 3, in format_user_badge
    badge = "User #" + user_id
TypeError: can only concatenate str (not "int") to str
""",
        test_code="""import pytest
from solution import format_user_badge

def test_format_badge():
    assert format_user_badge("Alice", 42) == "User #42"

def test_format_badge_zero():
    assert format_user_badge("Admin", 0) == "User #0"
""",
        expected_fix_summary="Convert user_id to string using str(user_id) or formatted f-string."
    ),

    "missing_import": BuggySample(
        id="missing_import",
        title="6. Missing Import (Math Module Not Imported)",
        category="NameError",
        description="Function computes Euclidean distance using math.sqrt without importing math module.",
        code="""def calculate_hypotenuse(a, b):
    \"\"\"Computes hypotenuse length using Pythagorean theorem.\"\"\"
    return math.sqrt(a**2 + b**2)
""",
        traceback="""Traceback (most recent call last):
  File "solution.py", line 3, in calculate_hypotenuse
    return math.sqrt(a**2 + b**2)
NameError: name 'math' is not defined
""",
        test_code="""import pytest
from solution import calculate_hypotenuse

def test_3_4_5_triangle():
    assert calculate_hypotenuse(3, 4) == 5.0

def test_5_12_13_triangle():
    assert calculate_hypotenuse(5, 12) == 13.0
""",
        expected_fix_summary="Add 'import math' at the top of the file."
    )
}


def get_sample_list() -> List[BuggySample]:
    return list(SAMPLE_PROGRAMS.values())


def get_sample_by_id(sample_id: str) -> BuggySample:
    return SAMPLE_PROGRAMS.get(sample_id, list(SAMPLE_PROGRAMS.values())[0])

