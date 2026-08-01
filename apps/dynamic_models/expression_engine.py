"""
Expression Engine — secure evaluation of user-defined formula expressions.
...
"""
import ast
import operator
import math
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Safe builtins available in expression sandbox
SAFE_BUILTINS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "True": True,
    "False": False,
    "None": None,
    "upper": str.upper,
    "lower": str.lower,
}

# Allowed AST node types (whitelist approach)
ALLOWED_NODES = {
    "Expression", "Constant", "Name", "Load",
    "BinOp", "UnaryOp", "BoolOp", "Compare",
    "Call", "Attribute",
    "Add", "Sub", "Mult", "Div", "Mod", "Pow",
    "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
    "And", "Or", "Not",
    "USub", "UAdd",
    "IfExp",
}


def evaluate_expression(expression: str, context: dict) -> Any:
    """
    Safely evaluate a user-defined expression.

    Uses AST whitelist to prevent code injection.
    Only basic math, string ops, and comparisons are allowed.

    Args:
        expression: The formula string (e.g., "revenue * 0.15")
        context: Dict of column_name → value for the current row

    Returns:
        The computed value
    """
    import ast

    if not expression or not expression.strip():
        return None

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        logger.warning("Invalid expression syntax: '%s' — %s", expression, e)
        return None

    # Validate AST — only allow whitelisted node types
    for node in ast.walk(tree):
        node_type = type(node).__name__
        if node_type not in ALLOWED_NODES:
            logger.warning(
                "Blocked node type '%s' in expression '%s'", node_type, expression
            )
            return None

    # Compile and evaluate in restricted namespace
    try:
        code = compile(tree, "<formula>", "eval")
        safe_globals = {"__builtins__": SAFE_BUILTINS}
        safe_locals = {**context}
        result = eval(code, safe_globals, safe_locals)
        return result
    except Exception as e:
        logger.warning("Expression eval failed: '%s' — %s", expression, e)
        return None


def evaluate_expressions(formula_columns, row_data: dict) -> dict[str, Any]:
    """
    Evaluate all formula columns for a single row.

    Args:
        formula_columns: QuerySet of DynamicColumnMetadata with column_type='formula'
        row_data: Dict of all column values for this row

    Returns:
        Dict of column_name → computed_value for changed values
    """
    results = {}
    for col in formula_columns:
        # Formula is stored in default_value field for formula-type columns
        formula = col.default_value or ""
        value = evaluate_expression(formula, row_data)

        current = row_data.get(col.column_name)
        if value != current:
            results[col.column_name] = value

    return results
