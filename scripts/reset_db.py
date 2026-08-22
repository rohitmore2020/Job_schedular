import sys
import subprocess
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import asyncio
from sqlalchemy import text
from rich.console import Console

from backend.app.core.database import engine
from scripts.seed_demo import seed_database

console = Console()


async def reset_database():
    console.print("🔄 [bold red]Resetting Database Schema...[/bold red]")
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
    console.print("✅ Public schema recreated.")

    console.print("📦 [bold blue]Applying Alembic Migrations...[/bold blue]")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root_dir, check=True)
    console.print("✅ Migrations applied successfully.")

    console.print("🌱 [bold green]Seeding fresh data...[/bold green]")
    await seed_database()
    console.print("🎉 [bold green]Database successfully reset, migrated, and seeded![/bold green]")


if __name__ == "__main__":
    asyncio.run(reset_database())
