def split_text(text: str, 
               chunk_size: int = 800, 
               chunk_overlap: int = 100,
               separator: list = ["\n\n", "\n", ". ", "。", "! ", "！", "? ", "？", ", ", "，", "; ", "；", ": ", "：", "、", " ", ""]
               ) -> list[str]:
    """
    Split text into chunks using recursive character splitting
    
    This is a custom implementation to avoid langchain dependencies
    that cause segfaults on Python 3.13
    """
    if not text:
        return []
    
    # If text is small enough, return as single chunk
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []
    
    chunks = []
    
    def _split_text_recursive(text: str, separators: list) -> list[str]:
        """Recursively split text using the given separators"""
        if not separators:
            # Base case: no more separators, split by character count
            result = []
            for i in range(0, len(text), chunk_size - chunk_overlap):
                chunk = text[i:i + chunk_size]
                if chunk.strip():
                    result.append(chunk.strip())
            return result
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        if separator == "":
            # Empty separator means split by characters
            result = []
            for i in range(0, len(text), chunk_size - chunk_overlap):
                chunk = text[i:i + chunk_size]
                if chunk.strip():
                    result.append(chunk.strip())
            return result
        
        splits = text.split(separator)
        
        result = []
        current_chunk = ""
        
        for i, split in enumerate(splits):
            # Add separator back except for the last split
            piece = split + (separator if i < len(splits) - 1 else "")
            
            # If adding this piece would exceed chunk_size
            if len(current_chunk) + len(piece) > chunk_size:
                if current_chunk:
                    result.append(current_chunk.strip())
                    # Start new chunk with overlap
                    if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                        current_chunk = current_chunk[-chunk_overlap:] + piece
                    else:
                        current_chunk = piece
                else:
                    # Single piece is too large, try next separator
                    if len(piece) > chunk_size:
                        result.extend(_split_text_recursive(piece, remaining_separators))
                        current_chunk = ""
                    else:
                        current_chunk = piece
            else:
                current_chunk += piece
        
        if current_chunk.strip():
            result.append(current_chunk.strip())
        
        return result
    
    chunks = _split_text_recursive(text, separator)
    
    # Remove empty chunks and return
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    return chunks