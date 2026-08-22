"""Test package.

Present so pytest imports conftest as ``tests.conftest``. Without it, ``import conftest``
and ``from tests.conftest import ...`` load two separate module objects, and helper classes
compared with ``isinstance`` across that boundary silently fail to match.
"""
