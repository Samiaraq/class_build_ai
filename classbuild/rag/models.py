from pydantic import BaseModel, Field

class PageText(BaseModel):
    page_number:int=Field(ge=1)
    text:str 

class DocumentChunk(BaseModel):
    chunk_id:str
    source_filename:str
    page_number:int
    chunk_index:int
    text:str

    @property
    def char_count(self)-> int:
        return len(self.text)

class  ProcessedDocument(BaseModel):
    filename:str
    fingerprint:str
    page_count: int
    word_count: int
    char_count: int
    empty_pages: list[int]
    chunk_size: int
    chunk_overlap: int
    chunks: list[DocumentChunk]
    @property 
    def chunk_count(self)-> int:
        return len(self.chunks)
    def check_consistency(self) -> bool:
        chunk_pages = {chunk.page_number for chunk in self.chunks}

        if len(chunk_pages) + len(self.empty_pages) != self.page_count:
            raise ValueError("Page counts are inconsistent.")

        chunk_ids = [chunk.chunk_id for chunk in self.chunks]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Duplicate chunk IDs found.")

        return True
    def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk

        return None