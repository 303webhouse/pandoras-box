/**
 * Knowledgebase Page JavaScript
 * Handles browsing, searching, and viewing knowledgebase entries
 */

// API Configuration
const API_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000/api'
    : `${window.location.origin}/api`;

// State
let allEntries = [];
let categories = [];
let currentCategory = 'all';
let currentEntryId = null;

// DOM Elements
const categoryList = document.getElementById('kbCategoryList');
const searchInput = document.getElementById('kbSearchInput');
const searchBtn = document.getElementById('kbSearchBtn');
const searchResults = document.getElementById('kbSearchResults');
const searchQueryDisplay = document.getElementById('searchQueryDisplay');
const resultsList = document.getElementById('kbResultsList');
const clearSearchBtn = document.getElementById('kbClearSearch');
const browseSection = document.getElementById('kbBrowse');
const currentCategoryEl = document.getElementById('kbCurrentCategory');
const entryCountEl = document.getElementById('kbEntryCount');
const entriesGrid = document.getElementById('kbEntriesGrid');
const entryView = document.getElementById('kbEntryView');
const backBtn = document.getElementById('kbBackBtn');
const entryCategory = document.getElementById('entryCategory');
const entryTitle = document.getElementById('entryTitle');
const entryContent = document.getElementById('entryContent');
const relatedTermsList = document.getElementById('relatedTermsList');
const allCountEl = document.getElementById('allCount');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadKnowledgebase();
    setupEventListeners();
    
    // Check for direct entry link (e.g., /knowledgebase?entry=savita-indicator)
    const urlParams = new URLSearchParams(window.location.search);
    const entryId = urlParams.get('entry');
    if (entryId) {
        setTimeout(() => loadEntry(entryId), 500);
    }
});

// Event Listeners
function setupEventListeners() {
    // Search
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });
    clearSearchBtn.addEventListener('click', clearSearch);
    
    // Back button
    backBtn.addEventListener('click', showBrowseView);
}

// Load all knowledgebase data
async function loadKnowledgebase() {
    try {
        const response = await fetch(`${API_URL}/knowledgebase`);
        const data = await response.json();
        
        allEntries = data.entries || [];
        categories = data.categories || [];
        
        // Update all count
        allCountEl.textContent = allEntries.length;
        
        // Render categories
        renderCategories();
        
        // Render entries
        renderEntries(allEntries);
        
    } catch (error) {
        console.error('Error loading knowledgebase:', error);
        entriesGrid.innerHTML = '<p class="empty-state">Error loading knowledgebase. Please try again.</p>';
    }
}

// Render category list
function renderCategories() {
    // Count entries per category
    const categoryCounts = {};
    categories.forEach(cat => categoryCounts[cat] = 0);
    allEntries.forEach(entry => {
        if (categoryCounts.hasOwnProperty(entry.category)) {
            categoryCounts[entry.category]++;
        }
    });
    
    // Build category HTML
    let html = `
        <li class="kb-category-item ${currentCategory === 'all' ? 'active' : ''}" data-category="all">
            <span class="category-name">All Entries</span>
            <span class="category-count">${allEntries.length}</span>
        </li>
    `;
    
    categories.forEach(cat => {
        html += `
            <li class="kb-category-item ${currentCategory === cat ? 'active' : ''}" data-category="${cat}">
                <span class="category-name">${cat}</span>
                <span class="category-count">${categoryCounts[cat] || 0}</span>
            </li>
        `;
    });
    
    categoryList.innerHTML = html;
    
    // Add click handlers
    document.querySelectorAll('.kb-category-item').forEach(item => {
        item.addEventListener('click', () => {
            const category = item.dataset.category;
            selectCategory(category);
        });
    });
}

// Select a category
function selectCategory(category) {
    currentCategory = category;
    
    // Update active state
    document.querySelectorAll('.kb-category-item').forEach(item => {
        item.classList.toggle('active', item.dataset.category === category);
    });
    
    // Filter and render entries
    let filtered = allEntries;
    if (category !== 'all') {
        filtered = allEntries.filter(e => e.category === category);
    }
    
    currentCategoryEl.textContent = category === 'all' ? 'All Entries' : category;
    renderEntries(filtered);
    
    // Hide search results, show browse
    searchResults.style.display = 'none';
    browseSection.style.display = 'block';
    entryView.style.display = 'none';
}

// Render entries grid
function renderEntries(entries) {
    if (entries.length === 0) {
        entriesGrid.innerHTML = '<p class="empty-state">No entries found.</p>';
        entryCountEl.textContent = '0 entries';
        return;
    }
    
    entryCountEl.textContent = `${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}`;
    
    let html = '';
    entries.forEach(entry => {
        const preview = entry.shortDescription 
            ? entry.shortDescription.substring(0, 150) + (entry.shortDescription.length > 150 ? '...' : '')
            : '';
        
        html += `
            <div class="kb-entry-card" data-entry-id="${entry.id}">
                <span class="entry-category">${entry.category}</span>
                <h3 class="entry-title">${entry.term}</h3>
                <p class="entry-preview">${preview}</p>
            </div>
        `;
    });
    
    entriesGrid.innerHTML = html;
    
    // Add click handlers
    document.querySelectorAll('.kb-entry-card').forEach(card => {
        card.addEventListener('click', () => {
            loadEntry(card.dataset.entryId);
        });
    });
}

// Perform search
async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) return;
    
    try {
        const response = await fetch(`${API_URL}/knowledgebase/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        searchQueryDisplay.textContent = query;
        
        if (data.results.length === 0) {
            resultsList.innerHTML = '<p class="empty-state">No results found.</p>';
        } else {
            let html = '';
            data.results.forEach(result => {
                html += `
                    <div class="kb-result-item" data-entry-id="${result.entry.id}">
                        <div class="result-info">
                            <div class="result-term">${result.entry.term}</div>
                            <div class="result-category">${result.entry.category}</div>
                            <div class="result-preview">${result.entry.shortDescription || ''}</div>
                        </div>
                        <span class="result-score">Score: ${result.score}</span>
                    </div>
                `;
            });
            resultsList.innerHTML = html;
            
            // Add click handlers
            document.querySelectorAll('.kb-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    loadEntry(item.dataset.entryId);
                });
            });
        }
        
        // Show search results, hide browse
        searchResults.style.display = 'block';
        browseSection.style.display = 'none';
        entryView.style.display = 'none';
        
    } catch (error) {
        console.error('Search error:', error);
        resultsList.innerHTML = '<p class="empty-state">Search failed. Please try again.</p>';
    }
}

// Clear search
function clearSearch() {
    searchInput.value = '';
    searchResults.style.display = 'none';
    browseSection.style.display = 'block';
    entryView.style.display = 'none';
}

// Load single entry
async function loadEntry(entryId) {
    try {
        const response = await fetch(`${API_URL}/knowledgebase/entry/${entryId}`);
        if (!response.ok) throw new Error('Entry not found');
        
        const entry = await response.json();
        currentEntryId = entryId;
        
        // Update URL without reload
        const url = new URL(window.location);
        url.searchParams.set('entry', entryId);
        window.history.pushState({}, '', url);
        
        // Populate entry view
        entryCategory.textContent = entry.category;
        entryTitle.textContent = entry.term;
        
        // Convert markdown-like content to HTML
        const htmlContent = convertToHTML(entry.fullDescription || entry.shortDescription);
        entryContent.innerHTML = htmlContent;
        
        // Load related terms
        loadRelatedTerms(entry.relatedTerms || []);
        
        // Show entry view
        searchResults.style.display = 'none';
        browseSection.style.display = 'none';
        entryView.style.display = 'block';
        
        // Scroll to top
        window.scrollTo(0, 0);
        
    } catch (error) {
        console.error('Error loading entry:', error);
        alert('Entry not found');
    }
}

// Load related terms
async function loadRelatedTerms(relatedIds) {
    if (!relatedIds || relatedIds.length === 0) {
        relatedTermsList.innerHTML = '<span style="color: var(--text-secondary);">No related terms</span>';
        return;
    }
    
    // Find related entries from our cached data
    const relatedEntries = allEntries.filter(e => relatedIds.includes(e.id));
    
    let html = '';
    relatedEntries.forEach(entry => {
        html += `<span class="related-term" data-entry-id="${entry.id}">${entry.term}</span>`;
    });
    
    relatedTermsList.innerHTML = html || '<span style="color: var(--text-secondary);">No related terms</span>';
    
    // Add click handlers
    document.querySelectorAll('.related-term').forEach(term => {
        term.addEventListener('click', () => {
            loadEntry(term.dataset.entryId);
        });
    });
}

// Show browse view
function showBrowseView() {
    // Clear URL param
    const url = new URL(window.location);
    url.searchParams.delete('entry');
    window.history.pushState({}, '', url);
    
    currentEntryId = null;
    searchResults.style.display = 'none';
    browseSection.style.display = 'block';
    entryView.style.display = 'none';
}

// Convert markdown-like text to HTML
function convertToHTML(text) {
    if (!text) return '';
    
    // Split by double newlines for paragraphs
    let html = text;
    
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Code blocks
    html = html.replace(/```([^`]+)```/gs, '<pre><code>$1</code></pre>');
    
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Tables (simple conversion)
    const tableRegex = /\|(.+)\|\n\|[-|\s]+\|\n((?:\|.+\|\n?)+)/g;
    html = html.replace(tableRegex, (match, headerRow, bodyRows) => {
        const headers = headerRow.split('|').filter(h => h.trim());
        const rows = bodyRows.trim().split('\n').map(row => 
            row.split('|').filter(c => c.trim())
        );
        
        let table = '<table><thead><tr>';
        headers.forEach(h => table += `<th>${h.trim()}</th>`);
        table += '</tr></thead><tbody>';
        rows.forEach(row => {
            table += '<tr>';
            row.forEach(cell => table += `<td>${cell.trim()}</td>`);
            table += '</tr>';
        });
        table += '</tbody></table>';
        return table;
    });
    
    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.+<\/li>\n?)+/g, '<ul>$&</ul>');
    
    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    
    // Paragraphs (wrap remaining text blocks)
    const lines = html.split('\n\n');
    html = lines.map(line => {
        line = line.trim();
        if (!line) return '';
        if (line.startsWith('<')) return line;
        return `<p>${line}</p>`;
    }).join('\n');
    
    // Clean up single newlines within paragraphs
    html = html.replace(/([^>])\n([^<])/g, '$1<br>$2');
    
    return html;
}

// Handle browser back/forward
window.addEventListener('popstate', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const entryId = urlParams.get('entry');
    if (entryId) {
        loadEntry(entryId);
    } else {
        showBrowseView();
    }
});
