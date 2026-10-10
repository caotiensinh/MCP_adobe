from mcp_adobe.illustrator_trusted_cep_probe import patch_dispatch
import pytest

def test_restricted_direct_probe_preserves_default_dispatch():
    js = 'const _e=`mcp_handle_request(${JSON.stringify(N)})`;L.current.evalScript(_e,fn);'
    patched = patch_dispatch(js)
    assert 'N.command?.type==="connection_probe"' in patched
    assert 'N.script.includes("documentCount")' in patched
    assert 'N.script.includes("app.version")' in patched
    assert 'L.current.evalScript(_e,fn);' in patched
    assert 'mcp_handle_request(${JSON.stringify(N)})' in patched

def test_refuse_unknown_bundle_or_multiple_dispatchers():
    with pytest.raises(ValueError):
        patch_dispatch("unrelated script")
    with pytest.raises(ValueError):
        patch_dispatch('const x=`mcp_handle_request(${JSON.stringify(N)})`;'*2)
