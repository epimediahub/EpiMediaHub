"""Fail-closed source-verified confirmation for legacy DELETE endpoints.

Never bypasses original delete handler or its typed-confirmation validation.
Only the exact handler's statically defined f-string using its one numeric
route parameter is accepted. Any other runtime expression is unavailable.
"""
from __future__ import annotations
import ast
import inspect
import textwrap
from flask import current_app


HANDLERS = {
    "delete-customer": ("v073_delete_customer","customer_id"),
    "delete-reseller": ("v080_delete_reseller","reseller_id"),
    "delete-device": ("v074_delete_device","device_id"),
}


class ConfirmationUnavailable(RuntimeError):
    pass


def _is_form_confirm(node):
    return (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr=="get" and isinstance(node.func.value,ast.Attribute)
        and node.func.value.attr=="form"
        and isinstance(node.func.value.value,ast.Name)
        and node.func.value.value.id=="request"
        and bool(node.args) and isinstance(node.args[0],ast.Constant)
        and node.args[0].value=="confirm")


def expected_confirmation(action: str, entity_id: int) -> str:
    if (action not in HANDLERS or type(entity_id) is not int
            or not 1<=entity_id<2**63):
        raise ConfirmationUnavailable("invalid action")
    endpoint,param=HANDLERS[action]
    handler=current_app.view_functions.get(endpoint)
    if not callable(handler):
        raise ConfirmationUnavailable("missing original business handler")
    try:
        tree=ast.parse(textwrap.dedent(inspect.getsource(handler)))
    except (OSError,TypeError,IndentationError,SyntaxError):
        raise ConfirmationUnavailable("original source unavailable") from None
    functions=[n for n in ast.walk(tree)
               if isinstance(n,ast.FunctionDef) and n.name==endpoint]
    if len(functions)!=1:
        raise ConfirmationUnavailable("cannot inspect original confirmation")
    matches=[]
    for node in ast.walk(functions[0]):
        if not isinstance(node,ast.Compare) or len(node.ops)!=1 or len(node.comparators)!=1:
            continue
        if not isinstance(node.ops[0],ast.NotEq):
            continue
        target=node.comparators[0] if _is_form_confirm(node.left) else (
            node.left if _is_form_confirm(node.comparators[0]) else None)
        if not isinstance(target,ast.JoinedStr):
            continue
        output=""
        references=0
        for part in target.values:
            if isinstance(part,ast.Constant) and isinstance(part.value,str):
                output+=part.value
            elif (isinstance(part,ast.FormattedValue)
                  and isinstance(part.value,ast.Name)
                  and part.value.id==param and part.format_spec is None
                  and part.conversion==-1):
                output+=str(entity_id)
                references+=1
            else:
                raise ConfirmationUnavailable("dynamic confirmation unsupported")
        if references!=1 or len(output)>100 or len(output)<2 or any(
                not c.isprintable() for c in output):
            raise ConfirmationUnavailable("unsupported confirmation expression")
        matches.append(output)
    if len(matches)!=1:
        raise ConfirmationUnavailable("original delete confirmation unverified")
    return matches[0]
