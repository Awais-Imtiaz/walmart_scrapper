"""Browser-side JavaScript injected via the Zyte API ``evaluate`` action.

The finder page's store search only fires from the page's own React code
(direct API replay gets Access Denied — Walmart's GraphQL requires
security headers their client generates; see docs/00-phase0-discovery.md
experiment R16). So we type the zip into the combobox the way React
notices (native value setter + input event), and the page re-renders
store cards for that zip on its own.
"""


def type_zip_script(zip_code: str) -> str:
    """Build the evaluate-action source that types *zip_code*.

    The status div lets the spider verify the script actually ran — page
    variants sometimes discard evaluate DOM writes, and a missing
    ``wm-steer-status`` div is the tell (experiment R15).
    """
    zip_code = str(zip_code)
    if not zip_code.isdigit():
        raise ValueError(f"zip must be digits, got {zip_code!r}")
    return f"""
const d = document.createElement('div');
d.id = 'wm-steer-status'; d.style.display = 'none';
document.body.appendChild(d);
try {{
  const input = document.querySelector(
    'input[data-automation-id="store-zip-code"]');
  if (!input) {{ d.innerText = 'NO-INPUT'; }}
  else {{
    input.focus();
    Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set
      .call(input, '{zip_code}');
    input.dispatchEvent(new Event('input', {{bubbles: true}}));
    d.innerText = 'TYPED';
  }}
}} catch (e) {{ d.innerText = 'ERR ' + String(e); }}
""".strip()


STEER_STATUS_DIV = "wm-steer-status"
TYPED_OK = "TYPED"
