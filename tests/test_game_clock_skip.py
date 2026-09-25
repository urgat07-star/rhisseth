import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/backend'))
from game_clock import _payload


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class ClockConnection:
    def __init__(self, now, online, vote_age_minutes=3):
        self.now = now
        self.online = online
        self.vote_age_minutes = vote_age_minutes

    def execute(self, sql, args=None):
        if 'FROM game_presence p' in sql:
            return Result([(user_id,) for user_id in self.online])
        if 'FROM player_baronies b' in sql:
            return Result([(1,), (2,)])
        if 'SELECT user_id FROM game_turn_votes' in sql:
            return Result([(1,)])
        if 'SELECT voted_at FROM game_turn_votes' in sql:
            return Result([(self.now - timedelta(minutes=self.vote_age_minutes),)])
        if 'SELECT now()' in sql:
            return Result([(self.now,)])
        raise AssertionError(sql)


class SkipTurnTests(unittest.TestCase):
    def test_skip_requires_offline_unvoted_opponent(self):
        now = datetime(2026, 9, 25, tzinfo=timezone.utc)
        state = _payload(ClockConnection(now, {1}), 1, now, now + timedelta(hours=12), 1)
        self.assertTrue(state['can_skip'])
        online_opponent = _payload(ClockConnection(now, {1, 2}), 1, now, now + timedelta(hours=12), 1)
        self.assertFalse(online_opponent['can_skip'])
        early = _payload(ClockConnection(now, {1}, vote_age_minutes=1), 1, now, now + timedelta(hours=12), 1)
        self.assertFalse(early['can_skip'])


if __name__ == '__main__':
    unittest.main()
