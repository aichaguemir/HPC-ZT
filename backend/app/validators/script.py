import re
import ast
from fastapi import HTTPException, UploadFile

from app.core.config import (
    MAX_FILE_SIZE,
    FORBIDDEN_MODULES,
    FORBIDDEN_FUNCTIONS,
    FORBIDDEN_ATTRIBUTES,
)


def ast_security_scan(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Python syntax error: {str(e)}"
        )

    for node in ast.walk(tree):

        # Block: import os / import subprocess
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in FORBIDDEN_MODULES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Forbidden module: '{alias.name}'"
                    )

        # Block: from os import system
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in FORBIDDEN_MODULES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Forbidden module: '{node.module}'"
                )

        # Block: obj.__subclasses__(), obj.__globals__(), obj.eval()
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES or node.attr in FORBIDDEN_FUNCTIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Forbidden attribute: '{node.attr}'"
                )

        # Block: eval(), exec(), globals()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_FUNCTIONS:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Forbidden function: '{node.func.id}'"
                    )

        # Block string-based dunder access: "__import__" as a string
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                for forbidden in FORBIDDEN_ATTRIBUTES:
                    if forbidden in node.value:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Forbidden string pattern: '{forbidden}'"
                        )


def validate_script(file: UploadFile, content: bytes) -> None:
    if not file.filename.endswith('.py'):
        raise HTTPException(
            status_code=400,
            detail="Only .py files allowed!"
        )

    if not re.match(r'^[\w\-\.]+\.py$', file.filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename! Use only letters, numbers, dash, underscore."
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty!")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large! Maximum 10MB")

    try:
        decoded = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8!")

    ast_security_scan(decoded)
