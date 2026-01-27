"""
Knowledgebase API - Serves documentation for indicators, strategies, signals, etc.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import json
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache the knowledgebase data
_knowledgebase_cache = None
_cache_loaded = False

def get_knowledgebase_path() -> str:
    """Get the path to the knowledgebase JSON file"""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledgebase.json"),
        os.path.join(os.getcwd(), "..", "data", "knowledgebase.json"),
        os.path.join(os.getcwd(), "data", "knowledgebase.json"),
        "/app/data/knowledgebase.json",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return os.path.abspath(path)
    
    return None

def load_knowledgebase() -> dict:
    """Load and cache the knowledgebase data"""
    global _knowledgebase_cache, _cache_loaded
    
    if _cache_loaded and _knowledgebase_cache is not None:
        return _knowledgebase_cache
    
    kb_path = get_knowledgebase_path()
    if not kb_path:
        logger.error("Knowledgebase file not found")
        return {"version": "1.0.0", "categories": [], "entries": []}
    
    try:
        with open(kb_path, 'r', encoding='utf-8') as f:
            _knowledgebase_cache = json.load(f)
            _cache_loaded = True
            logger.info(f"Loaded knowledgebase with {len(_knowledgebase_cache.get('entries', []))} entries")
            return _knowledgebase_cache
    except Exception as e:
        logger.error(f"Error loading knowledgebase: {e}")
        return {"version": "1.0.0", "categories": [], "entries": []}

def reload_knowledgebase():
    """Force reload of knowledgebase data (for updates)"""
    global _knowledgebase_cache, _cache_loaded
    _knowledgebase_cache = None
    _cache_loaded = False
    return load_knowledgebase()


@router.get("/knowledgebase")
async def get_all_entries(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search term for filtering entries")
):
    """
    Get all knowledgebase entries, optionally filtered by category or search term
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    # Filter by category if provided
    if category:
        entries = [e for e in entries if e.get("category", "").lower() == category.lower()]
    
    # Filter by search term if provided
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries 
            if search_lower in e.get("term", "").lower() 
            or search_lower in e.get("shortDescription", "").lower()
            or search_lower in e.get("category", "").lower()
        ]
    
    return {
        "version": kb.get("version", "1.0.0"),
        "lastUpdated": kb.get("lastUpdated"),
        "categories": kb.get("categories", []),
        "count": len(entries),
        "entries": entries
    }


@router.get("/knowledgebase/categories")
async def get_categories():
    """
    Get list of all categories
    """
    kb = load_knowledgebase()
    categories = kb.get("categories", [])
    
    # Count entries per category
    entries = kb.get("entries", [])
    category_counts = {}
    for entry in entries:
        cat = entry.get("category", "Uncategorized")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return {
        "categories": [
            {"name": cat, "count": category_counts.get(cat, 0)}
            for cat in categories
        ]
    }


@router.get("/knowledgebase/entry/{entry_id}")
async def get_entry(entry_id: str):
    """
    Get a single knowledgebase entry by ID (includes full description)
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    
    raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found")


@router.get("/knowledgebase/popup/{entry_id}")
async def get_popup(entry_id: str):
    """
    Get popup-friendly version of an entry (short description only, max 500 words)
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    for entry in entries:
        if entry.get("id") == entry_id:
            return {
                "id": entry.get("id"),
                "term": entry.get("term"),
                "category": entry.get("category"),
                "shortDescription": entry.get("shortDescription"),
                "relatedTerms": entry.get("relatedTerms", []),
                "hasFullDescription": bool(entry.get("fullDescription"))
            }
    
    raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found")


@router.get("/knowledgebase/search")
async def search_entries(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, description="Maximum number of results")
):
    """
    Search knowledgebase entries by term, description, or category
    Returns ranked results with relevance scoring
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    q_lower = q.lower()
    q_words = q_lower.split()
    
    results = []
    for entry in entries:
        score = 0
        term = entry.get("term", "").lower()
        short_desc = entry.get("shortDescription", "").lower()
        full_desc = entry.get("fullDescription", "").lower()
        category = entry.get("category", "").lower()
        
        # Exact term match - highest score
        if q_lower == term:
            score += 100
        # Term starts with query
        elif term.startswith(q_lower):
            score += 50
        # Query in term
        elif q_lower in term:
            score += 30
        
        # Category match
        if q_lower in category:
            score += 20
        
        # Words in short description
        for word in q_words:
            if word in short_desc:
                score += 5
            if word in full_desc:
                score += 2
        
        if score > 0:
            results.append({
                "entry": {
                    "id": entry.get("id"),
                    "term": entry.get("term"),
                    "category": entry.get("category"),
                    "shortDescription": entry.get("shortDescription")[:200] + "..." if len(entry.get("shortDescription", "")) > 200 else entry.get("shortDescription")
                },
                "score": score
            })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return {
        "query": q,
        "count": len(results[:limit]),
        "results": results[:limit]
    }


@router.get("/knowledgebase/related/{entry_id}")
async def get_related_entries(entry_id: str):
    """
    Get entries related to a specific entry
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    # Find the source entry
    source_entry = None
    for entry in entries:
        if entry.get("id") == entry_id:
            source_entry = entry
            break
    
    if not source_entry:
        raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found")
    
    related_ids = source_entry.get("relatedTerms", [])
    
    # Find related entries
    related_entries = []
    for entry in entries:
        if entry.get("id") in related_ids:
            related_entries.append({
                "id": entry.get("id"),
                "term": entry.get("term"),
                "category": entry.get("category")
            })
    
    return {
        "sourceId": entry_id,
        "sourceTerm": source_entry.get("term"),
        "relatedEntries": related_entries
    }


@router.post("/knowledgebase/reload")
async def reload_cache():
    """
    Force reload of knowledgebase cache (for after manual edits)
    """
    kb = reload_knowledgebase()
    return {
        "status": "reloaded",
        "entryCount": len(kb.get("entries", []))
    }


@router.get("/knowledgebase/term-map")
async def get_term_map():
    """
    Get a mapping of terms to their IDs for the frontend to use
    when making UI text clickable
    """
    kb = load_knowledgebase()
    entries = kb.get("entries", [])
    
    term_map = {}
    for entry in entries:
        term = entry.get("term", "")
        entry_id = entry.get("id", "")
        if term and entry_id:
            # Add the exact term
            term_map[term] = entry_id
            # Add lowercase version
            term_map[term.lower()] = entry_id
            # Add common variations
            if "_" in term:
                term_map[term.replace("_", " ")] = entry_id
    
    return {
        "count": len(term_map),
        "termMap": term_map
    }
