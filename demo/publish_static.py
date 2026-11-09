# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
"""Publish the generated synthetic demo as a self-contained, no-login static page.

Run demo/run_demo.py first. This command changes no engine inputs or outputs.
The published page is a recorded run, with explicit limitations and author credit.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'demo/out/dashboard.html'
page = source.read_text(encoding='utf-8')
assert '301 synthetic cases' in page
assert 'Prototype' in page and '<header>' in page and '</footer>' in page

notice = '''<aside class="card" style="margin:16px auto;max-width:1148px;padding:16px" aria-label="Demo scope">
<strong>Recorded synthetic demonstration</strong>
<p>This page displays a reproducible local engine run. It sends no messages, connects to no EHR and contains no real patient data.
The case workflow runs in the <a href="https://github.com/Agnuxo1/loopshield">open-source Python prototype</a>.
Arabic messages await native and clinical review. Masking leaves residual identifiers and does not anonymise data.</p>
<p><a href="#owners">Work list</a> · <a href="#messages">Patient messages</a> ·
<a href="#privacy">Privacy gateway</a> · <a href="#evidence">FHIR evidence</a> ·
<a href="https://github.com/Agnuxo1/loopshield#quick-start">Run locally</a></p></aside>'''
page = page.replace('</header>', '</header>\n' + notice, 1)
page = page.replace('<h2>Work list by accountable owner', '<h2 id="owners">Work list by accountable owner', 1)
page = page.replace('<h2>Patient message (English', '<h2 id="messages">Patient message (English', 1)
page = page.replace('<h2>Clinician note (stays', '<h2 id="privacy">Clinician note (stays', 1)
page = page.replace('<h2>FHIR R4 Task exported', '<h2 id="evidence">FHIR R4 Task exported', 1)
page = page.replace('not a medical device', 'research prototype; no clinical use')
page = page.replace('</footer>', '<br>© 2026 Francisco Angulo de Lafuente · '
                    '<a href="https://orcid.org/0009-0001-1634-7063">ORCID 0009-0001-1634-7063</a> · '
                    '<a href="https://github.com/Agnuxo1/loopshield/blob/main/LICENSE">MIT licence</a></footer>', 1)
page = page.replace('<title>LoopShield board</title>', '<title>LoopShield — synthetic prototype demo</title>')
(ROOT / 'docs/index.html').write_text(page, encoding='utf-8', newline='\n')
(ROOT / 'docs/.nojekyll').touch(exist_ok=True)
print('Published static demo: docs/index.html (301 synthetic cases; no external assets, forms or scripts)')
