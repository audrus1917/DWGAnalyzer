"""Exception classes."""

class ObjectNotFound(Exception):
    """Raised when an object is missing in the database."""


class FileNotFound(Exception):
    """Raised when a file is missing."""


class FolderNotFound(Exception):
    """Raised when a folder is missing."""


class UnsupportedFileType(Exception):
    """Raised when an unsupported file type is encountered."""

