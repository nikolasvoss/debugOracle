from __future__ import annotations


def validate_bounded_memory_read(
    address: str | int,
    size: int,
    *,
    max_bytes: int,
) -> tuple[int, int]:
    if isinstance(address, int):
        parsed_address = address
    else:
        try:
            parsed_address = int(str(address), 0)
        except ValueError as error:
            raise ValueError(f"Invalid memory address: {address!r}") from error
    if parsed_address < 0:
        raise ValueError("Memory address must be non-negative.")
    if size <= 0:
        raise ValueError("Memory read size must be greater than zero.")
    if size > max_bytes:
        raise ValueError(
            f"Memory read size {size} exceeds the safe limit of {max_bytes} bytes."
        )
    return parsed_address, size
