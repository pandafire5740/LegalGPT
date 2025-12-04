// Legal Knowledge Platform Frontend JavaScript

class LegalKnowledgeApp {
    constructor() {
        this.conversationHistory = [];
        this.apiBase = '/api';
        // Single stable model (server-side): Phi-3-mini
        this.currentModel = 'phi';
        // Enable streaming via SSE endpoint
        this.useStreaming = true;
        // Autocomplete state
        this.autocompleteSuggestions = [];
        this.selectedSuggestionIndex = -1;
        this.autocompleteVisible = false;
        // Document names in memory for autocomplete
        this.documentNames = [];
        this.init();
    }

    async init() {
        await this.loadSystemStats();
        await this.checkSystemHealth();
        await this.loadDocumentNames();
        this.setupEventListeners();
        // Align chat panel height to sidebar on initial load
        this.syncChatHeightToSidebar();
        
        // Setup chat input handler - try immediately and also after DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setupChatInputHandler());
        } else {
            this.setupChatInputHandler();
        }
        // Also try after a delay as backup
        setTimeout(() => this.setupChatInputHandler(), 500);
    }

    setupChatInputHandler() {
        // Try multiple times to ensure element exists
        const trySetup = () => {
            const chatInput = document.getElementById('chat-input');
            if (!chatInput) {
                setTimeout(trySetup, 100);
                return;
            }
            
            // Store reference to this for use in handler
            const self = this;
            
            // Handle Enter key to send message (Shift+Enter for new line)
            const handleKeyDown = function(event) {
                if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
                    event.preventDefault();
                    event.stopPropagation();
                    event.stopImmediatePropagation();
                    self.sendMessage();
                    return false;
                }
            };
            
            // Remove old listener if it exists (by cloning)
            const oldInput = chatInput;
            const newInput = oldInput.cloneNode(true);
            oldInput.parentNode.replaceChild(newInput, oldInput);
            
            // Re-attach input handler for auto-resize
            newInput.addEventListener('input', this.autoResizeTextarea.bind(this));
            
            // Attach keydown handler with capture phase and non-passive
            newInput.addEventListener('keydown', handleKeyDown, true);
            
            // Also try keypress as backup
            newInput.addEventListener('keypress', function(event) {
                if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
                    event.preventDefault();
                    self.sendMessage();
                }
            }, true);
        };
        
        trySetup();
    }

    setupEventListeners() {
        // Auto-resize textarea (will be re-setup in setupChatInputHandler)
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.addEventListener('input', this.autoResizeTextarea.bind(this));
        }
        
        // Modal click outside to close
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeModal(e.target.id);
            }
            // Close autocomplete when clicking outside
            if (!e.target.closest('.autocomplete-container')) {
                this.hideAutocomplete();
            }
        });

        // Keep chat height pegged to sidebar on resize
        window.addEventListener('resize', () => {
            this.syncChatHeightToSidebar();
            // Reposition autocomplete on resize
            if (this.autocompleteVisible) {
                this.positionAutocomplete();
            }
        });

        // Reposition autocomplete on scroll
        window.addEventListener('scroll', () => {
            if (this.autocompleteVisible) {
                this.positionAutocomplete();
            }
        }, true);
    }

    // Make Chat panel height equal to sidebar, so input bottom aligns with sidebar bottom
    syncChatHeightToSidebar() {
        try {
            const sidebar = document.querySelector('.sidebar');
            const chatMode = document.getElementById('chat-mode');
            if (!chatMode) return;
            if (!sidebar) {
                chatMode.style.height = '';
                chatMode.style.flex = '';
                return;
            }
            if (chatMode.classList.contains('active')) {
                const sidebarRect = sidebar.getBoundingClientRect();
                const chatRect = chatMode.getBoundingClientRect();
                const desired = Math.max(200, Math.floor(sidebarRect.bottom - chatRect.top));
                if (desired > 0 && Number.isFinite(desired)) {
                    chatMode.style.height = desired + 'px';
                    chatMode.style.flex = '0 0 auto';
                }
            } else {
                // clear explicit height when not in chat
                chatMode.style.height = '';
                chatMode.style.flex = '';
            }
        } catch (e) {
            // non-fatal: layout helper
        }
    }

    async loadSystemStats() {
        try {
            const response = await fetch(`${this.apiBase}/documents/stats/simple`);
            const data = await response.json();
            
            if (data.status === 'success') {
                // stats/simple returns flat fields: document_count and chunk_count
                const docCount = typeof data.document_count === 'number' ? data.document_count : 0;
                const chunkCount = typeof data.chunk_count === 'number' ? data.chunk_count : 0;
                const docEl = document.getElementById('document-count');
                const chunkEl = document.getElementById('chunk-count');
                if (docEl) docEl.textContent = docCount;
                if (chunkEl) chunkEl.textContent = chunkCount;

                // Populate custom tooltip with file names in memory
                const files = Array.isArray(data.files) ? data.files : [];
                this.setDocTooltip(files);
            }
        } catch (error) {
            console.error('Failed to load system stats:', error);
        }
    }

    setDocTooltip(files) {
        const tooltip = document.getElementById('doc-tooltip');
        if (!tooltip) return;
        if (!files.length) {
            tooltip.innerHTML = '<h4>No files in memory</h4>';
            return;
        }
        const safeItems = files.map(f => this.escapeHtml(f));
        tooltip.innerHTML = `
            <h4>Files in memory (${safeItems.length})</h4>
            <ul>${safeItems.map(name => `<li>${name}</li>`).join('')}</ul>
        `;
    }

    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    async checkSystemHealth() {
        try {
            const response = await fetch(`${this.apiBase}/health/detailed`);
            const data = await response.json();
            
            // Update status indicators
            const sharepointStatus = document.getElementById('sharepoint-status');
            const vectorStatus = document.getElementById('vector-status');
            
            if (data.checks) {
                // SharePoint disabled in minimal build
                if (sharepointStatus) {
                    sharepointStatus.classList.remove('healthy');
                }
                if (data.checks.vector_store) {
                    vectorStatus.classList.toggle('healthy', data.checks.vector_store.status === 'healthy');
                }
            }
        } catch (error) {
            console.error('Failed to check system health:', error);
        }
    }

    async loadDocumentNames() {
        try {
            const response = await fetch(`${this.apiBase}/legalgpt/extract/files-in-memory`);
            const data = await response.json();
            if (data.status === 'success' && Array.isArray(data.files)) {
                this.documentNames = data.files;
                // Update sidebar example with actual document name
                this.updateSidebarExamples();
            }
        } catch (error) {
            console.error('Failed to load document names:', error);
            // Fallback to empty array if fetch fails
            this.documentNames = [];
        }
    }

    updateSidebarExamples() {
        // Update the "Company ABC" example in sidebar with actual document name
        // Example questions are now static - no dynamic replacement needed
    }

    autoResizeTextarea(event) {
        const textarea = event.target;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    handleKeyDown(event) {
        // Send on Enter, but allow Shift+Enter for new lines
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.stopPropagation();
            this.sendMessage();
            return false;
        }
    }

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        
        if (!message) return;
        
        // Disable input and show loading
        this.setInputDisabled(true);
        // For streaming, avoid overlay so tokens are visible immediately
        if (!this.useStreaming) {
            const loadingMsg = this.conversationHistory.length === 0 
                ? 'LegalGPT is loading the AI model for the first time (2-5 minutes)... Future queries will be instant!' 
                : 'LegalGPT is generating a response...';
            this.showLoading(true, loadingMsg);
        }
        
        // Add user message to chat
        this.addMessage('user', message);
        
        // Clear input
        input.value = '';
        input.style.height = 'auto';
        
        try {
            if (this.useStreaming) {
                await this.streamChat(message);
            } else {
                await this.sendMessageNonStreaming(message);
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('assistant', 'Sorry, I\'m having trouble connecting to the server. Please check your connection and try again.');
        }
        
        this.setInputDisabled(false);
        this.showLoading(false);
    }

    async sendMessageNonStreaming(message) {
        const response = await fetch(`${this.apiBase}/chat/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_history: this.conversationHistory.slice(-6)
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            this.addMessage('assistant', data.answer, data.source_documents);
            this.conversationHistory.push({ role: 'user', content: message });
            this.conversationHistory.push({ role: 'assistant', content: data.answer });
        } else {
            this.addMessage('assistant', 'Sorry, I encountered an error processing your request. Please try again.');
        }
    }

    async streamChat(message) {
        // Create placeholder assistant message for streaming
        const messagesContainer = document.getElementById('chat-messages');
        const assistantDiv = document.createElement('div');
        assistantDiv.className = 'message assistant';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.style.whiteSpace = "normal";
        // Show animated thinking dots while waiting for first token
        contentDiv.innerHTML = '<span class="thinking-dots"><span></span><span></span><span></span></span>';
        assistantDiv.appendChild(contentDiv);
        const metadataDiv = document.createElement('div');
        metadataDiv.className = 'message-metadata';
        metadataDiv.textContent = new Date().toLocaleTimeString();
        assistantDiv.appendChild(metadataDiv);
        messagesContainer.appendChild(assistantDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        let fullText = '';
        try {
            const response = await fetch(`${this.apiBase}/chat/query/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    conversation_history: this.conversationHistory.slice(-6)
                })
            });
            if (!response.ok || !response.body) {
                // Fallback to non-streaming
                await this.sendMessageNonStreaming(message);
                assistantDiv.remove();
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buffer.indexOf('\n\n')) !== -1) {
                    const event = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);
                    if (event.startsWith('data: ')) {
                        const token = event.slice(6);
                        fullText += token;
                        // Progressive rendering (no normalization during streaming)
                        // Remove thinking dots once we have content
                        const md = fullText;
                        const html = marked.parse(md); // markdown -> HTML
                        contentDiv.innerHTML = html;   // render HTML (not textContent)
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    }
                }
            }
            
            // Final render (already done progressively above, but ensure it's correct)
            const md = this.normalizeMarkdown(fullText);
            const html = marked.parse(md); // markdown -> HTML
            contentDiv.innerHTML = html;   // render HTML (not textContent)
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            // Update conversation history
            this.conversationHistory.push({ role: 'user', content: message });
            this.conversationHistory.push({ role: 'assistant', content: fullText });
        } catch (e) {
            console.error('Streaming error:', e);
            // Replace placeholder with error message
            contentDiv.textContent = 'Sorry, streaming failed. Falling back to normal response...';
            await this.sendMessageNonStreaming(message);
            assistantDiv.remove();
        }
    }

    addMessage(role, content, sourceDocuments = null) {
        const messagesContainer = document.getElementById('chat-messages');
        
        // Remove welcome message if it exists
        const welcomeMessage = messagesContainer.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.style.whiteSpace = "normal";
        
        const md = this.normalizeMarkdown(content);
        const html = marked.parse(md);    // markdown -> HTML
        messageContent.innerHTML = html;  // render HTML (not textContent)
        
        messageDiv.appendChild(messageContent);
        
        // Add source documents if provided
        if (sourceDocuments && sourceDocuments.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'source-documents';
            
            const sourcesTitle = document.createElement('h4');
            sourcesTitle.innerHTML = '<i class="fas fa-file-text"></i> Source Documents:';
            sourcesDiv.appendChild(sourcesTitle);
            
            sourceDocuments.forEach(doc => {
                const docDiv = document.createElement('div');
                docDiv.className = 'source-document';
                
                docDiv.innerHTML = `
                    <div class="source-document-name">${doc.file_name}</div>
                    <div class="source-document-excerpt">${doc.excerpt}</div>
                    <div class="source-document-path">${doc.file_path}</div>
                `;
                
                sourcesDiv.appendChild(docDiv);
            });
            
            messageDiv.appendChild(sourcesDiv);
        }
        
        // Add timestamp
        const metadataDiv = document.createElement('div');
        metadataDiv.className = 'message-metadata';
        metadataDiv.textContent = new Date().toLocaleTimeString();
        messageDiv.appendChild(metadataDiv);
        
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    normalizeMarkdown(content) {
        if (!content) return '';

        let md = content;

        // 1) Ensure there's a newline before "- " if it follows non-newline text
        //    e.g. "Agreement- **Parties**" -> "Agreement\n- **Parties**"
        md = md.replace(/([^\n])(- \*\*)/g, '$1\n$2');

        // 2) Same for bullets that don't use bold
        md = md.replace(/([^\n])(- [A-Za-z0-9])/g, '$1\n$2');

        // 3) Optionally insert a blank line before the first bullet after a sentence
        md = md.replace(/(\.)\n(- \*\*)/g, '$1\n\n$2');

        return md;
    }

    sendExampleQuery(element) {
        const query = element.textContent.replace(/"/g, '');
        document.getElementById('chat-input').value = query;
        this.sendMessage();
    }

    setInputDisabled(disabled) {
        const input = document.getElementById('chat-input');
        const button = document.getElementById('send-button');
        
        input.disabled = disabled;
        button.disabled = disabled;
    }

    sendExampleQuery(element) {
        const query = element.textContent.replace(/"/g, '');
        document.getElementById('chat-input').value = query;
        this.sendMessage();
    }

    setInputDisabled(disabled) {
        const input = document.getElementById('chat-input');
        const button = document.getElementById('send-button');
        
        input.disabled = disabled;
        button.disabled = disabled;
    }

    showLoading(show, message = null) {
        const overlay = document.getElementById('loading-overlay');
        overlay.classList.toggle('active', show);
        if (show && message) {
            const loadingText = overlay.querySelector('p');
            if (loadingText) loadingText.textContent = message;
        } else if (!show) {
            const loadingText = overlay.querySelector('p');
            if (loadingText) loadingText.textContent = 'LegalGPT is generating a response...';
        }
    }

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
        }
    }

    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.remove('active');
    }

    showTermsExtraction() {
        this.showModal('terms-modal');
    }

    showDocumentSearch() {
        this.showModal('search-modal');
    }

    async extractTerms() {
        const filter = document.getElementById('terms-filter').value.trim();
        
        this.showLoading(true);
        this.closeModal('terms-modal');
        
        try {
            const url = new URL(`${window.location.origin}${this.apiBase}/chat/terms-conditions`);
            if (filter) {
                url.searchParams.append('filter_query', filter);
            }
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.status === 'success') {
                let message = `Found terms and conditions from ${data.total_documents} documents`;
                if (filter) {
                    message += ` matching "${filter}"`;
                }
                message += ':\n\n';
                
                data.terms_by_document.forEach((doc, index) => {
                    message += `**${index + 1}. ${doc.file_name}**\n${doc.terms_conditions}\n\n`;
                });
                
                this.addMessage('assistant', message);
            } else {
                this.addMessage('assistant', 'Sorry, I couldn\'t extract terms and conditions at this time.');
            }
            
        } catch (error) {
            console.error('Error extracting terms:', error);
            this.addMessage('assistant', 'Sorry, there was an error extracting terms and conditions.');
        }
        
        // Clear the input
        document.getElementById('terms-filter').value = '';
        this.showLoading(false);
    }

    async findDocument() {
        const query = document.getElementById('document-query').value.trim();
        
        if (!query) return;
        
        this.showLoading(true);
        this.closeModal('search-modal');
        
        try {
            const url = new URL(`${window.location.origin}${this.apiBase}/chat/document-location`);
            url.searchParams.append('query', query);
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.status === 'success' && data.files_found.length > 0) {
                let message = `Found ${data.total_matches} document(s) matching "${query}":\n\n`;
                
                data.files_found.forEach((file, index) => {
                    message += `**${index + 1}. ${file.file_name}**\n`;
                    message += `📁 Location: ${file.file_path}\n`;
                    message += `📅 Last Modified: ${file.last_modified}\n`;
                    message += `👤 Author: ${file.author}\n\n`;
                });
                
                this.addMessage('assistant', message);
            } else {
                this.addMessage('assistant', `Sorry, I couldn't find any documents matching "${query}".`);
            }
            
        } catch (error) {
            console.error('Error finding document:', error);
            this.addMessage('assistant', 'Sorry, there was an error searching for documents.');
        }
        
        // Clear the input
        document.getElementById('document-query').value = '';
        this.showLoading(false);
    }

    async syncDocuments() {
        this.addMessage('assistant', 'SharePoint sync is disabled in this build. Please use Upload Local Documents.');
    }

    showDocumentUpload() {
        try {
            // Reset the upload modal state
            const fileInput = document.getElementById('file-upload');
            const progressDiv = document.getElementById('upload-progress');
            const progressFill = document.getElementById('progress-fill');
            const progressText = document.getElementById('progress-text');
            
            if (fileInput) fileInput.value = '';
            if (progressDiv) progressDiv.style.display = 'none';
            if (progressFill) progressFill.style.width = '0%';
            if (progressText) progressText.textContent = 'Uploading...';
            
            this.showModal('upload-modal');
        } catch (error) {
            console.error('Error in app.showDocumentUpload:', error);
        }
    }

    async showManageFiles() {
        this.showModal('manage-files-modal');
        await this.loadFilesList();
    }

    startRename(fileName) {
        const fileItem = document.querySelector(`[data-file-name="${this.escapeHtml(fileName)}"]`);
        if (!fileItem) return;
        
        const display = fileItem.querySelector('.file-name-display');
        const edit = fileItem.querySelector('.file-name-edit');
        const input = fileItem.querySelector('.file-name-input');
        
        if (display && edit && input) {
            display.style.display = 'none';
            edit.style.display = 'flex';
            input.focus();
            input.select();
        }
    }

    cancelRename(fileName) {
        const fileItem = document.querySelector(`[data-file-name="${this.escapeHtml(fileName)}"]`);
        if (!fileItem) return;
        
        const display = fileItem.querySelector('.file-name-display');
        const edit = fileItem.querySelector('.file-name-edit');
        const input = fileItem.querySelector('.file-name-input');
        
        if (display && edit && input) {
            input.value = fileName; // Reset to original
            edit.style.display = 'none';
            display.style.display = 'inline-flex';
        }
    }

    async saveRename(oldFileName) {
        const fileItem = document.querySelector(`[data-file-name="${this.escapeHtml(oldFileName)}"]`);
        if (!fileItem) return;
        
        const input = fileItem.querySelector('.file-name-input');
        if (!input) return;
        
        const newFileName = input.value.trim();
        
        // Validate
        if (!newFileName) {
            alert('File name cannot be empty');
            return;
        }
        
        if (newFileName === oldFileName) {
            this.cancelRename(oldFileName);
            return;
        }
        
        // Show loading state
        const saveBtn = fileItem.querySelector('.file-name-save');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        try {
            const response = await fetch(`${this.apiBase}/documents/${encodeURIComponent(oldFileName)}/rename`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ new_name: newFileName })
            });
            
            const responseText = await response.text();
            
            if (!response.ok) {
                let errorMessage = 'Failed to rename file';
                try {
                    const errorData = JSON.parse(responseText);
                    errorMessage = errorData.detail || errorMessage;
                } catch (e) {
                    errorMessage = responseText || errorMessage;
                }
                throw new Error(errorMessage);
            }
            
            const data = JSON.parse(responseText);
            
            if (data.status === 'success') {
                // Update the file item's data attribute
                fileItem.setAttribute('data-file-name', this.escapeHtml(newFileName));
                
                // Update the display text
                const nameText = fileItem.querySelector('.file-name-text');
                if (nameText) {
                    nameText.textContent = newFileName;
                }
                
                // Update the input value
                input.value = newFileName;
                
                // Hide edit mode
                const display = fileItem.querySelector('.file-name-display');
                const edit = fileItem.querySelector('.file-name-edit');
                if (display && edit) {
                    edit.style.display = 'none';
                    display.style.display = 'inline-flex';
                }
                
                // Update remove button onclick
                const removeBtn = fileItem.querySelector('.file-remove-btn');
                if (removeBtn) {
                    removeBtn.setAttribute('onclick', `app.removeFile('${this.escapeHtml(newFileName)}')`);
                }
                
                // Refresh file list and system stats
                await this.loadFilesList();
                await this.loadSystemStats();
                
                // Show success message
                this.addMessage('assistant', `✅ Successfully renamed "${oldFileName}" to "${newFileName}". ${data.chunks_updated || 0} chunk(s) updated.`);
            } else {
                throw new Error(data.detail || 'Failed to rename file');
            }
        } catch (error) {
            console.error('Error renaming file:', error);
            alert(`Failed to rename file: ${error.message}`);
            // Restore button state
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-check"></i>';
            }
        }
    }

    async removeFile(fileName) {
        if (!confirm(`Are you sure you want to remove "${fileName}" from memory? This will remove all chunks from the vector database.`)) {
            return;
        }

        const container = document.getElementById('files-list-container');
        // Find the button for this file to show loading state
        const fileItems = container.querySelectorAll('.file-item');
        let removeBtn = null;
        fileItems.forEach(item => {
            const nameElement = item.querySelector('.file-name');
            if (nameElement && nameElement.textContent.includes(fileName)) {
                removeBtn = item.querySelector('.file-remove-btn');
            }
        });
        
        // Show loading state
        if (removeBtn) {
            removeBtn.disabled = true;
            removeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }

        try {
            const response = await fetch(`${this.apiBase}/documents/${encodeURIComponent(fileName)}`, {
                method: 'DELETE'
            });

            // Read response as text first (can only read once)
            const responseText = await response.text();

            // Check if response is ok before parsing JSON
            if (!response.ok) {
                let errorMessage = 'Failed to remove file';
                try {
                    const errorData = JSON.parse(responseText);
                    errorMessage = errorData.detail || errorMessage;
                } catch (e) {
                    // If response is not JSON, use the text directly
                    errorMessage = responseText || errorMessage;
                }
                throw new Error(errorMessage);
            }

            // Parse JSON from the text we already read
            const data = JSON.parse(responseText);

            if (data.status === 'success') {
                // Refresh file list and system stats
                await this.loadFilesList();
                await this.loadSystemStats();
                // Show success message
                this.addMessage('assistant', `✅ Successfully removed "${fileName}" from memory. ${data.deleted_chunks || 0} chunk(s) deleted.`);
            } else {
                throw new Error(data.detail || 'Failed to remove file');
            }
        } catch (error) {
            console.error('Error removing file:', error);
            alert(`Failed to remove file: ${error.message}`);
            // Refresh to restore button state
            await this.loadFilesList();
        }
    }

    async loadFilesList() {
        const container = document.getElementById('files-list-container');
        if (!container) return;

        container.innerHTML = '<div class="loading-message">Loading files...</div>';

        try {
            const response = await fetch(`${this.apiBase}/documents/local`);
            const data = await response.json();

            if (data.status === 'success' && data.files && data.files.length > 0) {
                let html = '<div class="files-list">';
                html += `<div class="files-header"><strong>${data.total_count} file(s) in memory</strong></div>`;
                html += '<div class="files-table">';
                
                data.files.forEach((file, index) => {
                    const fileSize = file.file_size ? this.formatFileSize(file.file_size) : 'Unknown';
                    const uploadDate = file.time_last_modified ? this.formatDate(file.time_last_modified) : 'Unknown';
                    const escapedFileName = this.escapeHtml(file.name);
                    // Use data attributes and event delegation to avoid issues with special characters
                    html += `
                        <div class="file-item" data-file-name="${escapedFileName}">
                            <div class="file-info">
                                <div class="file-name-container">
                                    <span class="file-name-display" data-action="rename" title="Click to rename">
                                        <i class="fas fa-file-alt"></i> <span class="file-name-text">${escapedFileName}</span>
                                    </span>
                                    <div class="file-name-edit" style="display: none;">
                                        <input type="text" class="file-name-input" value="${escapedFileName}" />
                                        <button class="file-name-save" data-action="save-rename" title="Save">
                                            <i class="fas fa-check"></i>
                                        </button>
                                        <button class="file-name-cancel" data-action="cancel-rename" title="Cancel">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="file-details">
                                    <span>Chunks: ${file.chunk_count || 0}</span>
                                    <span>Size: ${fileSize}</span>
                                    <span>Uploaded: ${uploadDate}</span>
                                </div>
                            </div>
                            <button class="file-remove-btn" data-action="remove" title="Remove from memory">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    `;
                });
                
                html += '</div></div>';
                container.innerHTML = html;
                
                // Set up event delegation for rename actions
                container.addEventListener('click', (e) => {
                    const fileItem = e.target.closest('.file-item');
                    if (!fileItem) return;
                    
                    const fileName = fileItem.getAttribute('data-file-name');
                    if (!fileName) return;
                    
                    if (e.target.closest('.file-name-display[data-action="rename"]')) {
                        this.startRename(fileName);
                    } else if (e.target.closest('.file-name-save[data-action="save-rename"]')) {
                        this.saveRename(fileName);
                    } else if (e.target.closest('.file-name-cancel[data-action="cancel-rename"]')) {
                        this.cancelRename(fileName);
                    } else if (e.target.closest('.file-remove-btn[data-action="remove"]')) {
                        this.removeFile(fileName);
                    }
                });
            } else {
                container.innerHTML = '<div class="empty-message">No files found. Upload documents to get started.</div>';
            }
        } catch (error) {
            console.error('Error loading files:', error);
            container.innerHTML = '<div class="error-message">Failed to load files. Please try again.</div>';
        }
    }

    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    formatDate(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return 'Unknown';
            const months = ['January', 'February', 'March', 'April', 'May', 'June', 
                          'July', 'August', 'September', 'October', 'November', 'December'];
            return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
        } catch (error) {
            return 'Unknown';
        }
    }

    async uploadDocuments() {
        const fileInput = document.getElementById('file-upload');
        const files = fileInput.files;
        
        if (files.length === 0) {
            alert('Please select at least one file to upload.');
            return;
        }

        const progressDiv = document.getElementById('upload-progress');
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');
        let warningsDiv = document.getElementById('upload-warnings');
        if (!warningsDiv) {
            warningsDiv = document.createElement('div');
            warningsDiv.id = 'upload-warnings';
            warningsDiv.style.marginTop = '0.5rem';
            warningsDiv.style.fontSize = '0.875rem';
            warningsDiv.style.color = 'var(--warning-color)';
            progressDiv.parentElement.appendChild(warningsDiv);
        } else {
            warningsDiv.textContent = '';
        }
        
        progressDiv.style.display = 'block';
        
        let uploadedCount = 0;
        const totalFiles = files.length;
        let duplicateNames = [];

        // Client-side duplicate pre-check removed; rely on server response instead
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            
            try {
                progressText.textContent = `Uploading ${file.name}... (${i + 1}/${totalFiles})`;
                
                const formData = new FormData();
                formData.append('file', file);
                
                const response = await fetch(`${this.apiBase}/documents/upload`, {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    uploadedCount++;
                    let msg = `✅ Successfully uploaded "${file.name}". Processing started in background.`;
                    if (result.llm_summary && result.llm_summary.trim()) {
                        msg += `\n\n**Quick summary**: ${result.llm_summary}`;
                    }
                    this.addMessage('assistant', msg);
                    // Immediately refresh counters after each successful upload
                    await this.loadSystemStats();
                } else if (result.status === 'exists') {
                    // Server-side duplicate check triggered
                    duplicateNames.push(file.name);
                    warningsDiv.textContent = `We already have this file in memory! ${duplicateNames.join(', ')}`;
                } else {
                    this.addMessage('assistant', 
                        `❌ Failed to upload "${file.name}": ${result.detail || 'Unknown error'}`
                    );
                }
                
                // Update progress
                const progress = ((i + 1) / totalFiles) * 100;
                progressFill.style.width = `${progress}%`;
                
            } catch (error) {
                console.error('Upload error:', error);
                this.addMessage('assistant', 
                    `❌ Error uploading "${file.name}": ${error.message}`
                );
            }
        }
        
        progressText.textContent = `Upload complete! ${uploadedCount}/${totalFiles} files uploaded successfully.`;
        
        // Refresh counters after upload completes
        if (uploadedCount > 0) {
            await this.loadSystemStats();
        }
        
        // Close modal after a delay
        setTimeout(() => {
            this.closeModal('upload-modal');
            progressDiv.style.display = 'none';
            fileInput.value = ''; // Clear file input
            
            // Reset progress bar
            progressFill.style.width = '0%';
            progressText.textContent = 'Uploading...';
            
            // Final refresh of stats
            this.loadSystemStats();
        }, 3000);
    }

    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.remove('active');
    }

    // Autocomplete functionality - powerful text autocomplete with partial word matching
    getAutocompleteSuggestions(query) {
        const suggestions = [];
        // Don't trim - we need spaces to extract fragments from multi-word queries
        const queryLower = query.toLowerCase();
        
        // Require 3+ characters (check trimmed length)
        const trimmedQuery = queryLower.trim();
        if (!trimmedQuery || trimmedQuery.length < 3) {
            return [];
        }
        
        // Debug logging
        console.log('getAutocompleteSuggestions called with:', query, 'queryLower:', queryLower, 'documentNames:', this.documentNames?.length || 0);

        // Helper function to check if text matches query (partial word matching)
        const matchesQuery = (text, searchTerm) => {
            const textLower = text.toLowerCase();
            // Check if search term appears anywhere in text (partial word matching)
            return textLower.includes(searchTerm.toLowerCase());
        };

        // Helper function to calculate match score (higher = better)
        const getMatchScore = (text, searchTerm) => {
            const textLower = text.toLowerCase();
            const searchLower = searchTerm.toLowerCase();
            let score = 0;
            
            // Exact match gets highest score
            if (textLower === searchLower) return 1000;
            
            // Starts with search term gets high score
            if (textLower.startsWith(searchLower)) score += 500;
            
            // Word boundary match gets medium score
            const wordBoundaryRegex = new RegExp(`\\b${searchLower.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'i');
            if (wordBoundaryRegex.test(text)) score += 200;
            
            // Partial word match gets lower score
            if (textLower.includes(searchLower)) score += 100;
            
            // Prefer shorter matches
            score -= text.length / 10;
            
            return score;
        };

        // Extract potential document name fragments from query
        // Look for words that could be part of document names (3+ characters)
        const extractDocumentFragments = (query) => {
            const fragments = [];
            // Split by spaces and punctuation, keep words 3+ chars
            const words = query.split(/[\s,._-]+/).filter(word => word.length >= 3);
            
            // Also check for consecutive capital letters (like "MSA", "NDA")
            const capsMatch = query.match(/[A-Z]{2,}/g);
            if (capsMatch) {
                fragments.push(...capsMatch.map(w => w.toLowerCase()));
            }
            
            // Add individual words
            fragments.push(...words);
            
            // Add the full query as a potential fragment
            if (query.length >= 3) {
                fragments.push(query);
            }
            
            // Remove duplicates and return
            return [...new Set(fragments)];
        };

        // 1. PRIORITY: Match document names using fragments from anywhere in query
        if (this.documentNames && this.documentNames.length > 0) {
            const docMatches = [];
            const fragments = extractDocumentFragments(queryLower);
            console.log('Extracted fragments:', fragments, 'from query:', queryLower);
            
            // Try matching each fragment against document names
            fragments.forEach(fragment => {
                this.documentNames.forEach(docName => {
                    // Remove file extension for matching and display
                    const docNameWithoutExt = docName.replace(/\.[^/.]+$/, '');
                    const docNameLower = docNameWithoutExt.toLowerCase();
                    
                    // Check if fragment matches document name
                    if (matchesQuery(docNameWithoutExt, fragment)) {
                        const score = getMatchScore(docNameWithoutExt, fragment);
                        
                        // Check if we already have this document with a better score
                        const existingIndex = docMatches.findIndex(d => d.fullText === docNameWithoutExt);
                        if (existingIndex >= 0) {
                            // Update if this match has a better score
                            if (score > docMatches[existingIndex].score) {
                                docMatches[existingIndex].score = score;
                                docMatches[existingIndex].matchFragment = fragment;
                            }
                        } else {
                            docMatches.push({
                                text: docNameWithoutExt,
                                fullText: docNameWithoutExt,
                                type: 'document',
                                icon: 'fas fa-file-contract',
                                score: score,
                                matchType: 'document',
                                matchFragment: fragment
                            });
                        }
                    }
                });
            });
            
            // Sort by score and add top matches
            console.log('Document matches found:', docMatches.length);
            docMatches
                .sort((a, b) => b.score - a.score)
                .slice(0, 5)
                .forEach(match => {
                    suggestions.push(match);
                });
        } else {
            console.log('No document names available or empty array');
        }

        // 2. Match query templates (existing templates)
        const baseQueries = [
            "Show me all contracts with termination clauses",
            "Extract payment terms from vendor agreements",
            "Find documents mentioning confidentiality",
            "What are the key terms in the NDA?",
            "List all contracts expiring this year",
            "Find clauses about intellectual property",
            "Show me all employment agreements",
            "What are the renewal terms?",
            "Find documents with non-compete clauses",
            "Summarize the contract with Playlist DataTrust DPA"
        ];

        baseQueries.forEach(q => {
            if (matchesQuery(q, queryLower) && !suggestions.some(s => s.text === q)) {
                const score = getMatchScore(q, queryLower);
                suggestions.push({
                    text: q,
                    fullText: q,
                    type: 'template',
                    icon: 'fas fa-lightbulb',
                    score: score,
                    matchType: 'template'
                });
            }
        });

        // 3. Match conversation history
        const historyQueries = this.conversationHistory
            .filter(msg => msg.role === 'user')
            .map(msg => msg.content.trim())
            .filter(q => matchesQuery(q, queryLower) && q.toLowerCase() !== queryLower);

        historyQueries.forEach(q => {
            if (!suggestions.some(s => s.text === q)) {
                const score = getMatchScore(q, queryLower);
                suggestions.push({
                    text: q,
                    fullText: q,
                    type: 'history',
                    icon: 'fas fa-history',
                    score: score,
                    matchType: 'history'
                });
            }
        });

        // Sort by: document matches first, then by score
        suggestions.sort((a, b) => {
            // Documents always come first
            if (a.matchType === 'document' && b.matchType !== 'document') return -1;
            if (a.matchType !== 'document' && b.matchType === 'document') return 1;
            // Then sort by score
            return b.score - a.score;
        });

        // Return top 5-10 suggestions
        const result = suggestions.slice(0, 10);
        console.log('getAutocompleteSuggestions returning:', result.length, 'suggestions', result);
        return result;
    }

    highlightMatch(text, query) {
        if (!query || !text) return text;
        
        const queryLower = query.toLowerCase();
        const textLower = text.toLowerCase();
        
        // Find all matches (case-insensitive, partial word matching)
        const matches = [];
        let searchIndex = 0;
        
        while (searchIndex < textLower.length) {
            const index = textLower.indexOf(queryLower, searchIndex);
            if (index === -1) break;
            
            matches.push({
                start: index,
                end: index + query.length
            });
            
            searchIndex = index + 1; // Continue searching after this match
        }
        
        if (matches.length === 0) return text;
        
        // Build highlighted string (work backwards to preserve indices)
        let result = text;
        for (let i = matches.length - 1; i >= 0; i--) {
            const match = matches[i];
            const before = result.substring(0, match.start);
            const matchText = result.substring(match.start, match.end);
            const after = result.substring(match.end);
            result = `${before}<span class="autocomplete-item-match">${matchText}</span>${after}`;
        }
        
        return result;
    }

    showAutocomplete(suggestions, query) {
        const dropdown = document.getElementById('autocomplete-dropdown');
        const input = document.getElementById('chat-input');
        if (!dropdown || !input) return;

        if (suggestions.length === 0) {
            dropdown.innerHTML = '<div class="autocomplete-empty">No suggestions found</div>';
            dropdown.classList.add('show');
            this.autocompleteVisible = true;
            this.positionAutocomplete();
            return;
        }

        dropdown.innerHTML = suggestions.map((suggestion, index) => {
            const displayText = suggestion.text || suggestion.fullText || '';
            // For document matches, highlight the fragment that matched, otherwise use full query
            const highlightTerm = (suggestion.matchType === 'document' && suggestion.matchFragment) 
                ? suggestion.matchFragment 
                : query;
            const highlighted = this.highlightMatch(displayText, highlightTerm);
            return `
                <div class="autocomplete-item ${index === this.selectedSuggestionIndex ? 'selected' : ''}" 
                     data-index="${index}"
                     onclick="app.selectAutocompleteSuggestion(${index})">
                    <i class="${suggestion.icon} autocomplete-item-icon"></i>
                    <span class="autocomplete-item-text">${highlighted}</span>
                    <span class="autocomplete-item-meta">${suggestion.type || 'suggestion'}</span>
                </div>
            `;
        }).join('');

        dropdown.classList.add('show');
        this.autocompleteVisible = true;
        this.autocompleteSuggestions = suggestions;
        
        // Position dropdown above or below based on available space
        // Use requestAnimationFrame to ensure DOM is updated first
        requestAnimationFrame(() => {
            this.positionAutocomplete();
        });
    }

    positionAutocomplete() {
        const dropdown = document.getElementById('autocomplete-dropdown');
        const input = document.getElementById('chat-input');
        if (!dropdown || !input || !this.autocompleteVisible) return;

        // Reset positioning and max-height
        dropdown.classList.remove('position-above');
        dropdown.style.maxHeight = '250px';
        
        // Force a reflow to get accurate measurements
        void dropdown.offsetHeight;
        
        // Get positions
        const inputRect = input.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        
        // Calculate space below and above
        const spaceBelow = viewportHeight - inputRect.bottom - 10; // 10px margin
        const spaceAbove = inputRect.top - 10; // 10px margin
        
        // Estimate dropdown height (rough calculation)
        const itemHeight = 48; // Approximate height per item
        const estimatedHeight = Math.min(
            this.autocompleteSuggestions.length * itemHeight + 20, // +20 for padding
            250 // max-height
        );
        
        // If not enough space below but enough above, position above
        if (spaceBelow < estimatedHeight && spaceAbove > estimatedHeight) {
            dropdown.classList.add('position-above');
        } else if (spaceBelow < estimatedHeight && spaceAbove < estimatedHeight) {
            // Not enough space either way - use whichever has more space
            if (spaceAbove > spaceBelow) {
                dropdown.classList.add('position-above');
                dropdown.style.maxHeight = `${Math.max(150, spaceAbove - 10)}px`;
            } else {
                dropdown.style.maxHeight = `${Math.max(150, spaceBelow - 10)}px`;
            }
        } else if (spaceBelow < estimatedHeight) {
            // Not enough space below, reduce max-height
            dropdown.style.maxHeight = `${Math.max(150, spaceBelow - 10)}px`;
        }
    }

    hideAutocomplete() {
        const dropdown = document.getElementById('autocomplete-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
        }
        this.autocompleteVisible = false;
        this.selectedSuggestionIndex = -1;
        this.autocompleteSuggestions = [];
    }

    selectAutocompleteSuggestion(index) {
        if (index < 0 || index >= this.autocompleteSuggestions.length) return;
        
        const suggestion = this.autocompleteSuggestions[index];
        const input = document.getElementById('chat-input');
        if (!input) return;
        
        // Get current cursor position and input value
        const cursorPos = input.selectionStart;
        const currentValue = input.value;
        
        // Find the start of the current word being typed (backwards from cursor)
        let wordStart = cursorPos;
        while (wordStart > 0 && /\S/.test(currentValue[wordStart - 1])) {
            wordStart--;
        }
        
        // Find the end of the current word (forwards from cursor)
        let wordEnd = cursorPos;
        while (wordEnd < currentValue.length && /\S/.test(currentValue[wordEnd])) {
            wordEnd++;
        }
        
        // Get text before and after the word
        const textBefore = currentValue.substring(0, wordStart);
        const textAfter = currentValue.substring(wordEnd);
        
        // Insert suggestion text at cursor position (replacing the partial word)
        const suggestionText = suggestion.fullText || suggestion.text || '';
        const newValue = textBefore + suggestionText + textAfter;
        
        input.value = newValue;
        input.style.height = 'auto';
        this.autoResizeTextarea({ target: input });
        this.hideAutocomplete();
        
        // Set cursor position after inserted text
        const newCursorPos = wordStart + suggestionText.length;
        input.focus();
        input.setSelectionRange(newCursorPos, newCursorPos);
    }

    navigateAutocomplete(direction) {
        if (!this.autocompleteVisible || this.autocompleteSuggestions.length === 0) return;

        if (direction === 'up') {
            this.selectedSuggestionIndex = Math.max(-1, this.selectedSuggestionIndex - 1);
        } else if (direction === 'down') {
            this.selectedSuggestionIndex = Math.min(
                this.autocompleteSuggestions.length - 1,
                this.selectedSuggestionIndex + 1
            );
        }

        // Update UI
        const dropdown = document.getElementById('autocomplete-dropdown');
        if (dropdown) {
            const items = dropdown.querySelectorAll('.autocomplete-item');
            items.forEach((item, index) => {
                item.classList.toggle('selected', index === this.selectedSuggestionIndex);
            });
            
            // Scroll into view if needed
            if (this.selectedSuggestionIndex >= 0) {
                const selectedItem = items[this.selectedSuggestionIndex];
                if (selectedItem) {
                    selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            }
        }
    }
}

// Global functions for HTML event handlers
function handleKeyDown(event) {
    if (typeof app !== 'undefined' && app) {
        const result = app.handleKeyDown(event);
        if (result === false || (event.key === 'Enter' && !event.shiftKey)) {
            return false;
        }
    }
}

function showDocumentUpload() {
    if (typeof app !== 'undefined') {
        app.showDocumentUpload();
    }
}

function uploadDocuments() {
    app.uploadDocuments();
}

function closeModal(modalId) {
    app.closeModal(modalId);
}

function sendMessage() {
    app.sendMessage();
}

function sendExampleQuery(element) {
    app.sendExampleQuery(element);
}

function showTermsExtraction() {
    app.showTermsExtraction();
}

function showDocumentSearch() {
    app.showDocumentSearch();
}

function closeModal(modalId) {
    app.closeModal(modalId);
}

function extractTerms() {
    app.extractTerms();
}

function findDocument() {
    app.findDocument();
}

function syncDocuments() {
    app.syncDocuments();
}

// Model switching removed: single model enforced server-side

// Initialize app when DOM is loaded
const app = new LegalKnowledgeApp();

// Auto-refresh stats every 5 minutes
setInterval(() => {
    app.loadSystemStats();
    app.checkSystemHealth();
}, 300000);
