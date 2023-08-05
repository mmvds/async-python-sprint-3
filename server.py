import asyncio
import logging
import time
from typing import Coroutine

import aiosqlite

from client import Client

logger = logging.getLogger(__name__)


async def initialize_database():
    """
    Creates sqlite DB and tables if not exist
    :return:
    """
    try:
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('''CREATE TABLE IF NOT EXISTS messages
                                        (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, message TEXT, 
                                        timestamp INTEGER)''')

                await cursor.execute('''CREATE TABLE IF NOT EXISTS users
                                        (id INTEGER PRIMARY KEY AUTOINCREMENT, nickname TEXT UNIQUE, password TEXT)''')

                await cursor.execute('''CREATE TABLE IF NOT EXISTS warnings
                                        (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, 
                                        timestamp INTEGER)''')
        logger.info('Database initialized successfully.')
    except aiosqlite.Error as err:
        logger.error(f'Database error: \n{err}')
    except (FileNotFoundError, PermissionError) as err:
        logger.error(f'Database file access error: \n{err}')


class Server:
    """
    Server class to create simple chat server
    """

    def __init__(self, host: str = '127.0.0.1', port: int = 8000, message_limit: int = 20, message_expiry: int = 3600):
        self.host = host
        self.port = port
        self.clients = {}
        self.message_limit = message_limit
        self.message_expiry = message_expiry

    async def listen(self) -> Coroutine:
        """
        Run server forever
        :return:
        """
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )

        addr = server.sockets[0].getsockname()
        logger.info(f'Server started on {addr} message limit {self.message_limit}, expiry {self.message_expiry}')

        async with server:
            await server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Coroutine:
        """
        Handle client connection
        :param reader: client StreamReader
        :param writer: client StreamWriter
        :return:
        """
        addr = writer.get_extra_info('peername')
        logger.info(f'New client connected: {addr}')
        try:
            client = Client(reader, writer)
            self.clients[addr] = client

            try:
                await client.send_history(self.message_expiry, self.message_limit)
                async for message in client.read_messages():
                    if not message:
                        break
                    await self.process_message(client, message)
            except asyncio.CancelledError as err:
                logger.error(f'Connection cancelled \n{err}')
            except aiosqlite.Error as err:
                logger.error(f'Database error: {err}')

        except ConnectionError as err:
            logger.error(f'Connection error with client {addr}: \n{err}')

        finally:
            logger.info(f'Client disconnected: {addr}')
            self.clients.pop(addr, None)
            writer.close()
            await writer.wait_closed()

    async def save_message(self, sender_nickname: str, receiver_nickname: str, message: str) -> Coroutine:
        """
        Save message to Database
        :param sender_nickname:
        :param receiver_nickname:
        :param message:
        :return:
        """
        timestamp = int(time.time())
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('''INSERT INTO messages (sender, receiver, message, timestamp)
                                       VALUES (?, ?, ?, ?)''', (sender_nickname, receiver_nickname, message, timestamp))
                await connection.commit()

    async def process_message(self, sender: Client, message: str) -> Coroutine:
        """
        Process text/command messages
        :param sender:
        :param message:
        :return:
        """
        if not message.startswith('/'):
            message = f'/send {message}'
        command, *args = message[1:].split(' ')
        if command not in ['register', 'connect', 'help'] and not sender.nickname:
            await sender.send('Please use /connect or /register firstly. Use /help to get a full list of commands')
        elif command == 'send':
            await self.handle_send_command(sender, args)
        elif command == 'private':
            await self.handle_private_command(sender, args)
        elif command == 'register':
            await self.handle_register_command(sender, args)
        elif command == 'connect':
            await self.handle_connect_command(sender, args)
        elif command == 'voteban':
            await self.handle_voteban_command(sender, args)
        elif command == 'help':
            await self.handle_help_command(sender)
        elif command == 'status':
            await sender.send(f'Active connections: {len(self.clients)}')
        else:
            await sender.send('Unknown command. Use /help to get a list')

    async def handle_register_command(self, sender: Client, args: list) -> Coroutine:
        if len(args) != 2:
            await sender.send('Usage: /register <nickname> <password>')
            return

        nickname, password = args[0], args[1]
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('SELECT nickname FROM users WHERE nickname = ?', (nickname,))
                existing_user = await cursor.fetchone()
                if existing_user:
                    await sender.send('Nickname already taken.')
                else:
                    await cursor.execute('INSERT INTO users (nickname, password) VALUES (?, ?)', (nickname, password))
                    await connection.commit()
                    await sender.send('Registered')
                    sender.nickname = nickname

    async def handle_connect_command(self, sender: Client, args: list) -> Coroutine:
        if len(args) != 2:
            await sender.send('Usage: /connect <nickname> <password>')
            return

        nickname, password = args[0], args[1]
        async with aiosqlite.connect('chat.db') as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('SELECT nickname FROM users WHERE nickname = ? AND password = ?',
                                     (nickname, password))
                registered_user = await cursor.fetchone()

                if registered_user:
                    if sender.nickname:
                        await sender.load_user_info(nickname)
                    else:
                        await sender.send('Connected')
                        sender.nickname = nickname
                else:
                    await sender.send('Invalid nickname or password.')

    async def handle_send_command(self, sender: Client, args: list) -> Coroutine:
        if not args:
            await sender.send('Usage: /send <message>')
            return

        message = ' '.join(args)
        await self.broadcast(f'{sender.nickname}: {message}')
        await self.save_message(sender.nickname, None, message)

    async def handle_private_command(self, sender: Client, args: list) -> Coroutine:
        if len(args) < 2:
            await sender.send('Usage: /private <nickname> <message>')
            return
        else:
            receiver_nickname, message = args[0], args[1:]
            if recievers := self.find_client_by_nickname(receiver_nickname):
                is_sender_notified = False
                for receiver in recievers:
                    await receiver.send(f'Private message from {sender.nickname}: {" ".join(message)}')
                    if not is_sender_notified:
                        await sender.send(f'Private message to {receiver_nickname}: {" ".join(message)}')
                        is_sender_notified = True
                    await self.save_message(sender.nickname, receiver_nickname, ' '.join(message))
            else:
                await sender.send(f'User "{receiver_nickname}" not found or offline.')

    async def handle_help_command(self, sender: Client) -> Coroutine:
        await sender.send('''/help - Available commands: 
        /register <nickname> <password> - Register new user
        /connect <nickname> <password> - Auth in the chat
        /send <message> - Send public message
        /private <nickname> <message> - Send private message to nickname
        /voteban <nickname> - Vote for 4 hours ban for nickname
        /status - Show amount of active connections''')

    async def handle_voteban_command(self, sender: Client, args: list) -> Coroutine:
        if len(args) != 1:
            await sender.send('Usage: /voteban <nickname>')
            return

        target_nickname = args[0]
        if target_clients := self.find_client_by_nickname(target_nickname):
            for target_client in target_clients:
                if not await target_client.already_voted(sender.nickname, 4 * 60 * 60):
                    await target_client.add_warning(sender.nickname)
                    if target_client.warnings >= 3:
                        await self.broadcast(f'{target_nickname} has been votebanned.')
                        await target_client.send('You have been votebanned for 4 hours.')
                        target_client.banned_until = time.time() + (4 * 60 * 60)
                        target_client.warnings = 0
                    else:
                        await self.broadcast(f'{sender.nickname} has voted to ban {target_nickname}. '
                                             f'({target_client.warnings}/3)')
                else:
                    await sender.send('You have already voted to ban this user in the last 4 hours.')
        else:
            await sender.send(f'User "{target_nickname}" not found or offline.')

    async def broadcast(self, message: str) -> Coroutine:
        for client in self.clients.values():
            if not client.banned_until:
                await client.send(message)

    def find_client_by_nickname(self, nickname: str) -> list:
        return [client for client in self.clients.values() if client.nickname == nickname]


async def main(host: str, port: int) -> Coroutine:
    server = Server(host=host, port=port)
    await initialize_database()
    await server.listen()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main('127.0.0.1', 8000))
