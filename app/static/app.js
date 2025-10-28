// Legal Knowledge Platform Frontend JavaScript

class LegalKnowledgeApp {
    constructor() {
        this.conversationHistory = [];
        this.apiBase = '/api';
        // Single stable model (server-side): Phi-3-mini
        this.currentModel = 'phi';
        // Enable streaming via SSE endpoint
        this.useStreaming = true;
        this.init();
    }

    async init() {
        await this.loadSystemStats();
        await this.checkSystemHealth();
        this.setupEventListeners();
        // Align chat panel height to sidebar on initial load
        this.syncChatHeightToSidebar();
    }

    setupEventListeners() {
        // Auto-resize textarea
        const chatInput = document.getElementById('chat-input');
        chatInput.addEventListener('input', this.autoResizeTextarea);
        
        // Modal click outside to close
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeModal(e.target.id);
            }
        });

        // Keep chat height pegged to sidebar on resize
        window.addEventListener('resize', () => this.syncChatHeightToSidebar());
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

    autoResizeTextarea(event) {
        const textarea = event.target;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    handleKeyDown(event) {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            this.sendMessage();
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
        contentDiv.innerHTML = '';
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
                        // Update plain text progressively for speed
                        contentDiv.textContent = fullText;
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    }
                }
            }
            // Final formatting
            contentDiv.innerHTML = this.formatMessageContent(fullText);
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
        
        // Format message content
        messageContent.innerHTML = this.formatMessageContent(content);
        
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

    formatMessageContent(content) {
        // Enhanced formatting with markdown-style support
        let formatted = content;
        
        // Convert **bold** to <strong> tags (more subtle)
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="highlight">$1</strong>');
        
        // Convert section headers (emoji + **text** at start of line)
        formatted = formatted.replace(/^([📁📋💡🔍✅❌⚠️🎯📊🚀]+)\s+\*\*(.+?)\*\*:?/gm, 
            '<div class="section-header"><span class="emoji">$1</span> <strong>$2</strong></div>');
        
        // Convert numbered lists (only if at start of line with clear spacing)
        formatted = formatted.replace(/^\s*(\d+)\.\s+(.+)$/gm, '<div class="list-item"><span class="list-number">$1.</span> $2</div>');
        
        // Convert bullet points (only if at start of line)
        formatted = formatted.replace(/^\s*[•]\s+(.+)$/gm, '<div class="list-item"><span class="bullet">•</span> $1</div>');
        
        // Make URLs clickable
        formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" class="link">$1</a>');
        
        // Convert line breaks
        formatted = formatted.replace(/\n\n/g, '<br><br>');
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
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
        console.log('showModal called with:', modalId);
        const modal = document.getElementById(modalId);
        console.log('Modal element found:', !!modal);
        if (modal) {
            console.log('Adding active class to modal');
            modal.classList.add('active');
            console.log('Modal classes after adding active:', modal.className);
        } else {
            console.error('Modal element not found:', modalId);
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
        console.log('App.showDocumentUpload called');
        try {
            // Reset the upload modal state
            const fileInput = document.getElementById('file-upload');
            const progressDiv = document.getElementById('upload-progress');
            const progressFill = document.getElementById('progress-fill');
            const progressText = document.getElementById('progress-text');
            
            console.log('Elements found:', {
                fileInput: !!fileInput,
                progressDiv: !!progressDiv,
                progressFill: !!progressFill,
                progressText: !!progressText
            });
            
            if (fileInput) fileInput.value = '';
            if (progressDiv) progressDiv.style.display = 'none';
            if (progressFill) progressFill.style.width = '0%';
            if (progressText) progressText.textContent = 'Uploading...';
            
            console.log('Calling showModal with upload-modal');
            this.showModal('upload-modal');
            console.log('showModal completed');
        } catch (error) {
            console.error('Error in app.showDocumentUpload:', error);
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
        
        // Trigger search index rebuild if any files were uploaded
        if (uploadedCount > 0) {
            progressText.textContent += ' Rebuilding search index...';
            try {
                const rebuildResponse = await fetch(`${this.apiBase}/search/rebuild`, {
                    method: 'POST'
                });
                
                if (rebuildResponse.ok) {
                    const rebuildResult = await rebuildResponse.json();
                    progressText.textContent = `✅ Upload complete! Indexed ${rebuildResult.indexed_files} files with ${rebuildResult.total_chunks} chunks.`;
                    // Refresh counters after rebuild completes
                    await this.loadSystemStats();
                } else {
                    progressText.textContent += ' (Index rebuild failed - please rebuild manually)';
                }
            } catch (error) {
                console.error('Index rebuild error:', error);
                progressText.textContent += ' (Index rebuild failed - please rebuild manually)';
            }
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
}

// Global functions for HTML event handlers
function handleKeyDown(event) {
    app.handleKeyDown(event);
}

function showDocumentUpload() {
    console.log('showDocumentUpload function called');
    try {
        if (typeof app !== 'undefined') {
            console.log('App object exists, calling showDocumentUpload');
            app.showDocumentUpload();
        } else {
            console.error('App object is undefined');
        }
    } catch (error) {
        console.error('Error in showDocumentUpload:', error);
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
