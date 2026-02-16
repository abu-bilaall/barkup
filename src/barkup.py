from pathlib import Path
import shutil

def barkup_file(src: str, dest: str) -> None:
    src_path = Path(src)
    dest_path = Path(dest)

    if not src_path.is_file():
        raise FileNotFoundError(f"{src_path} does not exist or is not a file.")
    
    dest_path.mkdir(parents=True, exist_ok=True)

    file = src_path.name
    full_dest_path = dest_path.joinpath(file)
    
    shutil.copy2(src_path, full_dest_path)


def barkup_directory(src: str, dest: str) -> None:
    src_path = Path(src)
    dest_root = Path(dest)

    if dest_root.is_file():
        raise FileExistsError(f"Destination {dest_root} is a file.")

    if not src_path.is_dir():
        raise FileNotFoundError(f"{src_path} does not exist or is not a directory.")
    
    dest_path = dest_root / src_path.name
    dest_path.mkdir(parents=True, exist_ok=True)

    for entry in src_path.iterdir():
        if entry.is_file():
            barkup_file(str(entry), str(dest_path))
        else:
            barkup_directory(str(entry), str(dest_path))