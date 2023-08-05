# Консольный клиент-сервер

Приложение для получения и обработки сообщений от клиента.

Реализовано:
- [+] (1 балл) Период жизни доставленных сообщений — 1 час (по умолчанию).
- [+] (1 балл) Клиент может отправлять не более 20 (по умолчанию) сообщений в общий чат в течение определенного периода — 1 час (по умолчанию). В конце каждого периода лимит обнуляется.
- [+] (2 балла) Возможность пожаловаться на пользователя. При достижении лимита в 3 предупреждения, пользователь становится «забанен» — невозможность отправки сообщений в течение 4 часов (по умолчанию).
- [+] (4 балла) Пользователь может подключиться с двух и более клиентов одновременно. Состояния должны синхронизироваться между клиентами.

# Запуск сервера с параметрами по умолчанию
```bash
python server.py
```

# Подключение к серверу
Linux можно воспользоваться командой netcat (nc)
```bash
nc localhost 8000
```
Windows необходимо включить в "Программах и компонентах" сервис telnet
```bash
telnet localhost 8000
```
P.s. для ревьювера - 
Обновил read_messages в классе Client для ожидания символа нажатия Enter (\n) 
для совместимости с telnet Windows 10, т.к. он обрабатывал каждый отправленный символ,
а не строку как netcat в linux

# Список методов для взаимодействия
1. Получить список команд.
```python
/help
```
2. Зарегистрировать пользователя
```python
/register <nickname> <password>
```
3. Подключиться используя данные авторизации
```python
/connect <nickname> <password>
```
4. Отправить сообщение в общий чат
```python
/send <message>
```
5. Отправить приватное сообщение
```python
/private <nickname> <message>
```
6. Проголосовать за блокировку пользователя
```python
/voteban <nickname>
```
7. Показывает количество активных соединений
```python
/status
```
8. Сообщение отправленное без команды работает аналогично /send

# Пример использования в linux:
В первом окне терминала, пользователь admin
```
nc localhost 8000
/help
/help - Available commands:
        /register <nickname> <password> - Register new user
        /connect <nickname> <password> - Auth in the chat
        /send <message> - Send public message
        /private <nickname> <message> - Send private message to nickname
        /voteban <nickname> - Vote for 4 hours ban for nickname
        /status - Show amount of active connections
/register admin admin
Registered
hi all
admin: hi all
admin: hi one more time
Private message from tester: hi admin!
```
Во втором окне терминала, тот же пользователь admin
```
nc localhost 8000
Recent chat history:
admin: hi all
/connect admin admin
Connected
hi one more time
admin: hi one more time
Private message from tester: hi admin!
```
В третьем окне терминала пользователь tester
```
nc localhost 8000
Recent chat history:
admin: hi all
admin: hi one more time
/register tester tester
Registered
/private admin hi admin!
Private message to admin: hi admin!
```