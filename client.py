import asyncio
import logging
import time

import aiosqlite

logger = logging.getLogger(__name__)


class Client:
    """
    Class of client connections
    """
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.nickname = None
        self.last_message_time = 0
        self.banned_until = 0
        self.warnings = 0
        self.peername = writer.get_extra_info('peername')

    async def send(self, message):
        """
        Send message to self
        :param message: text of message
        :return:
        """
        if self.banned_until > time.time():
            await asyncio.sleep(self.banned_until - time.time())
            self.banned_until = 0
        if not self.banned_until:
            self.writer.write(message.encode() + b'\n')
            await self.writer.drain()

    async def send_history(self, message_expiry: int, message_limit: int):
        """
        Send history of last messages
        :param message_expiry: max message live time
        :param message_limit: amount of messages to show in history
        :return:
        """
        timestamp_limit = int(time.time()) - message_expiry
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('''SELECT sender, receiver, message FROM messages WHERE timestamp > ?  
                                        AND (receiver is NULL or (receiver = ? or sender = ?)) 
                                        ORDER BY timestamp DESC LIMIT ?''',
                                     (timestamp_limit, self.nickname, self.nickname, message_limit))
                history = await cursor.fetchall()
        if history:
            history.reverse()
            await self.send('Recent chat history:')
            for sender, receiver, message in history:
                if receiver:
                    await self.send(f'{sender} to {receiver}: {message}')
                else:
                    await self.send(f'{sender}: {message}')

    async def load_user_info(self, nickname: str):
        """
        Load users warning info
        :param nickname: user's nickname
        :return:
        """
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('SELECT COUNT(id) FROM warnings WHERE receiver = ?', (nickname,))
                self.warnings = await cursor.fetchone()
                self.warnings = self.warnings[0] if self.warnings else 0

    async def already_voted(self, sender_nickname: str, duration: int) -> bool:
        """
        Check if sender already voted for ban in duration sec time
        :param sender_nickname: voteban sender
        :param duration: duration to check votes in seconds
        :return: True, if sender already voted
        """
        timestamp_limit = int(time.time()) - duration
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('''SELECT id FROM warnings WHERE sender = ? AND receiver = ? AND timestamp > ?''',
                                     (sender_nickname, self.nickname, timestamp_limit))
                result = await cursor.fetchone()
        return result is not None

    async def read_messages(self):
        try:
            while True:
                data = await self.reader.read(1000)
                if not data:
                    continue
                message = data.decode().strip()
                self.last_message_time = int(time.time())
                yield message
        except asyncio.CancelledError as err:
            logger.error(f'Connection cancelled \n{err}')

    async def add_warning(self, sender_nickname: str):
        """
        Add warning for a receiver
        :param self: voteban receiver
        :param sender_nickname: voteban sender
        :return:
        """
        timestamp = int(time.time())
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('''INSERT INTO warnings (sender, receiver, timestamp) VALUES (?, ?, ?)''',
                                     (sender_nickname, self.nickname, timestamp))
                await connection.commit()
        self.warnings += 1
