import bcrypt
import asyncio
import asyncpg

async def main():
    password = b'AdminPassword123!'
    hashed = bcrypt.hashpw(password, bcrypt.gensalt()).decode()

    conn = await asyncpg.connect(
        host='postgres',
        port=5432,
        user='anon_user',
        password='letsgohard',
        database='anon_signal',
        ssl=None
    )

    await conn.execute(
        "UPDATE analyst_users SET password_hash = $1 WHERE username = 'admin'",
        hashed
    )

    row = await conn.fetchrow(
        "SELECT password_hash FROM analyst_users WHERE username = 'admin'"
    )

    valid = bcrypt.checkpw(password, row['password_hash'].encode())
    print('SUCCESS' if valid else 'FAILED')
    await conn.close()

asyncio.run(main())