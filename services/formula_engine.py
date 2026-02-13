import re
from odoo.exceptions import ValidationError

_ALLOWED_RE = re.compile(r'^[0-9+\-*/\s]+$')

def validate_strict_formula(formula: str):
    if not formula or not str(formula).strip():
        raise ValidationError("Empty formula is not allowed.")

    f = str(formula).strip()

    if not _ALLOWED_RE.match(f):
        raise ValidationError("Formula contains invalid characters.")

    tokens = re.findall(r'\d+|[+\-*/]', f.replace(' ', ''))

    if tokens[0] in '+-*/' or tokens[-1] in '+-*/':
        raise ValidationError("Formula cannot start or end with an operator.")

    for i, t in enumerate(tokens):
        if i % 2 == 0 and not t.isdigit():
            raise ValidationError("Formula sequence is invalid.")
        if i % 2 == 1 and t not in '+-*/':
            raise ValidationError("Formula sequence is invalid.")

    return tokens


def eval_strict_formula(formula, values_by_seq):
    tokens = validate_strict_formula(formula)

    prec = {'+':1,'-':1,'*':2,'/':2}
    output = []
    ops = []

    for t in tokens:
        if t.isdigit():
            seq = int(t)
            if seq not in values_by_seq:
                raise ValidationError(f"Sequence {seq} not found.")
            output.append(float(values_by_seq[seq]))
        else:
            while ops and prec[ops[-1]] >= prec[t]:
                output.append(ops.pop())
            ops.append(t)

    while ops:
        output.append(ops.pop())

    stack = []
    for t in output:
        if isinstance(t, float):
            stack.append(t)
        else:
            b = stack.pop()
            a = stack.pop()
            if t == '+': stack.append(a+b)
            elif t == '-': stack.append(a-b)
            elif t == '*': stack.append(a*b)
            elif t == '/': stack.append(a/b)

    return stack[0]
