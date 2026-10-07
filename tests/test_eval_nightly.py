import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class NightlyTests(unittest.TestCase):
    def test_all_sets_run_when_container_reads_stdin_and_one_set_alerts(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'aws').write_text('#!/bin/bash\necho unit-test-key\n')
            (directory / 'docker').write_text('''#!/bin/bash
cat >/dev/null
if [[ "$*" == *app.evalrun* ]]; then
  echo "$*" >> "$NIGHTLY_TEST_LOG"
  if [[ "$*" == *facts-core* ]]; then exit 3; fi
fi
''')
            for name in ('aws', 'docker'):
                (directory / name).chmod(0o755)
            script = (root / 'deploy/app/eval-nightly.sh').read_text().replace('cd /opt/gate/app', 'cd "' + temp + '"')
            log = directory / 'calls'
            env = dict(os.environ, PATH=temp + ':' + os.environ['PATH'], NIGHTLY_TEST_LOG=str(log))
            result = subprocess.run(['bash'], input=script, text=True, env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 3)
            self.assertIn('facts-core', calls[0])
            self.assertIn('facts-guard-v2', calls[1])
            self.assertIn('gate-page-v1', calls[2])
