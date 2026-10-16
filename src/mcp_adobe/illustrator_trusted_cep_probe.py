"""Prepare a safe read-only CEP direct probe, without clearing Python fences."""
import re

def patch_dispatch(bundle: str) -> str:
    # Match exact deployed single command dispatch. Never patch arbitrary code.
    pattern = r"(\w+)=`mcp_handle_request\(\$\{JSON\.stringify\((\w+)\)\}\)`;"
    matches = list(re.finditer(pattern, bundle))
    if len(matches) != 1:
        raise ValueError(f"Expected one dispatcher; found {len(matches)}")
    match = matches[0]
    variable, request = match.groups()
    # Only trusted host-read command. Preserve all normal request handling.
    gate = (f'{request}.command?.type==="connection_probe"'
            f'&&typeof {request}.script==="string"'
            f'&&{request}.script.includes("documentCount")'
            f'&&{request}.script.includes("app.version")')
    repl = (f"{variable}=({gate})?{request}.script:"
            + "`mcp_handle_request(${JSON.stringify(" + request + ")})`;")
    return bundle[:match.start()] + repl + bundle[match.end():]

