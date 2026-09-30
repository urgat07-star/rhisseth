import unittest
from pathlib import Path


class GitSyncCommitCommentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.sync=(cls.root/'tools/rhisseth-sync.ps1').read_text(encoding='utf-8')
        cls.pull=(cls.root/'tools/Sync-FromVds.ps1').read_text(encoding='utf-8')
        cls.push=(cls.root/'tools/Publish-ToGitHub.ps1').read_text(encoding='utf-8')

    def test_report_contains_full_sha_and_commit_comment(self):
        self.assertIn("git log -1 --pretty=format:'%H'",self.sync)
        self.assertIn('Комментарий коммита: $subject',self.sync)

    def test_user_comment_is_used_for_vds_import_and_github_commit(self):
        self.assertIn("[string]$CommitMessage = ''",self.pull)
        self.assertIn('$message = $CommitMessage.Trim()',self.pull)
        self.assertIn('[string]$CommitMessage = ""',self.push)
        self.assertIn('$message = $CommitMessage.Trim()',self.push)
        self.assertNotIn('Import VDS state $stamp',self.pull)


if __name__=='__main__':
    unittest.main()
