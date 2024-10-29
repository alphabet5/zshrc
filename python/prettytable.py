from rich.console import Console
from rich.table import Table
import sys


if __name__ == "__main__":
    data = sys.stdin.read()
    table = Table(
        box=None,
    )
    header = False
    for row in data.split("\n"):
        if not header:
            for col in row.split("\t"):
                table.add_column(col)
            header = True
        else:
            table.add_row(*row.split("\t"))
    console = Console()
    console.print(table)
