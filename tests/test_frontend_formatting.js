// Unit tests for frontend message formatting
// Run with: node tests/test_frontend_formatting.js

// Mock the formatMessageContent function logic
function formatMessageContent(content) {
    if (!content) return '';

    const escapeHtml = (text) => text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    const applyInlineFormatting = (text) => {
        let formatted = escapeHtml(text);
        formatted = formatted.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*([^*]+?)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        formatted = formatted.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" class="link">$1</a>');
        return formatted;
    };

    // Extract bullets function
    const extractBullets = (text) => {
        const bullets = [];
        const matches = [];
        let match;
        
        // Pattern 1: Markdown format with colon-dash ":- **Label**:"
        const colonDashPattern = /:\s*-\s*\*\*([^*]+?)\*\*:\s*/g;
        colonDashPattern.lastIndex = 0;
        while ((match = colonDashPattern.exec(text)) !== null) {
            matches.push({
                index: match.index,
                fullMatch: match[0],
                label: match[1].trim(),
                contentStart: match.index + match[0].length,
                isMarkdown: true
            });
        }
        
        // Pattern 2: Markdown format with period-space-dash ". - **Label**:"
        const periodDashPattern = /\.\s+-\s*\*\*([^*]+?)\*\*:\s*/g;
        periodDashPattern.lastIndex = 0;
        while ((match = periodDashPattern.exec(text)) !== null) {
            const isDuplicate = matches.some(m => {
                const overlapStart = Math.max(m.index, match.index);
                const overlapEnd = Math.min(m.index + m.fullMatch.length, match.index + match[0].length);
                return overlapStart < overlapEnd;
            });
            if (!isDuplicate) {
                matches.push({
                    index: match.index,
                    fullMatch: match[0],
                    label: match[1].trim(),
                    contentStart: match.index + match[0].length,
                    isMarkdown: true
                });
            }
        }
        
        // Pattern 3: Standard markdown format "- **Label**:" (at start of line or after whitespace)
        const standardMarkdownPattern = /(?:^|[\s\n]+)-\s*\*\*([^*]+?)\*\*:\s*/g;
        standardMarkdownPattern.lastIndex = 0;
        while ((match = standardMarkdownPattern.exec(text)) !== null) {
            const isDuplicate = matches.some(m => {
                const overlapStart = Math.max(m.index, match.index);
                const overlapEnd = Math.min(m.index + m.fullMatch.length, match.index + match[0].length);
                return overlapStart < overlapEnd;
            });
            if (!isDuplicate) {
                matches.push({
                    index: match.index,
                    fullMatch: match[0],
                    label: match[1].trim(),
                    contentStart: match.index + match[0].length,
                    isMarkdown: true
                });
            }
        }
        
        // Pattern 4: Standard format without markdown "- Label:" (fallback)
        if (matches.length === 0) {
            const standardPattern = /(?:^|\.\s+|[\s\n]+)([-•*])\s+([A-Z][A-Za-z\s&]{0,50}?):\s*/g;
            standardPattern.lastIndex = 0;
            while ((match = standardPattern.exec(text)) !== null) {
                matches.push({
                    index: match.index,
                    fullMatch: match[0],
                    label: match[2].trim(),
                    contentStart: match.index + match[0].length,
                    isMarkdown: false
                });
            }
        }
        
        // Sort matches by index to maintain order
        matches.sort((a, b) => a.index - b.index);
        
        if (matches.length === 0) {
            return null;
        }
        
        // Extract intro text before first bullet
        const introText = text.substring(0, matches[0].index).trim();
        if (introText && introText.length > 3) {
            bullets.push({ 
                type: 'text', 
                content: introText.replace(/\.\s*$/, '').trim() 
            });
        }
        
            // Extract content for each bullet
            matches.forEach((m, idx) => {
                const contentStart = m.contentStart;
                let content = '';
                
                if (idx < matches.length - 1) {
                    // Find where the next bullet starts
                    const nextBulletStart = matches[idx + 1].index;
                    const textToNextBullet = text.substring(contentStart, nextBulletStart);
                    
                    // Check if next bullet starts with ". -" pattern (period-space-dash)
                    const nextBulletFullMatch = matches[idx + 1].fullMatch;
                    const nextBulletStartsWithPeriod = text.substring(nextBulletStart - 1, nextBulletStart) === '.';
                    
                    if (nextBulletStartsWithPeriod && nextBulletFullMatch.startsWith('. ')) {
                        // Next bullet starts with ". -", so extract up to (but not including) that period
                        content = text.substring(contentStart, nextBulletStart - 1).trim();
                    } else {
                        // Find the last period in this range (which should be before the next bullet)
                        const lastPeriodIndex = textToNextBullet.lastIndexOf('.');
                        if (lastPeriodIndex !== -1) {
                            // Extract content up to (but not including) the period
                            content = text.substring(contentStart, contentStart + lastPeriodIndex).trim();
                        } else {
                            // No period found, extract up to next bullet start
                            content = text.substring(contentStart, nextBulletStart).trim();
                        }
                    }
                } else {
                    // Last bullet - content goes to end of text
                    content = text.substring(contentStart, text.length).trim();
                    // Remove trailing period if present
                    content = content.replace(/\.\s*$/, '').trim();
                }
            
            bullets.push({
                type: 'bullet',
                label: m.label,
                content: content
            });
        });
        
        return bullets.length > 0 ? bullets : null;
    };

    // Normalize content first
    const normalizedContent = content.replace(/\u00A0/g, ' ').replace(/\r\n/g, '\n');
    const globalBullets = extractBullets(normalizedContent);
    
    if (globalBullets && globalBullets.length > 0 && globalBullets.some(item => item.type === 'bullet')) {
        // Process bullets found in the entire content
        const output = [];
        let listBuffer = [];
        let listType = null;
        
        const flushList = () => {
            if (!listType || listBuffer.length === 0) return;
            const items = listBuffer.map(item => {
                if (item.includes('<strong>') || item.includes('<em>') || item.includes('<code>')) {
                    return `<li>${item}</li>`;
                }
                return `<li>${applyInlineFormatting(item)}</li>`;
            }).join('');
            if (listType === 'ol') {
                output.push(`<ol class="message-list numbered">${items}</ol>`);
            } else {
                output.push(`<ul class="message-list">${items}</ul>`);
            }
            listBuffer = [];
            listType = null;
        };
        
        const pushParagraphBreak = () => {
            if (output.length === 0 || output[output.length - 1] !== '<div class="paragraph-break"></div>') {
                output.push('<div class="paragraph-break"></div>');
            }
        };
        
        globalBullets.forEach((item, index) => {
            if (item.type === 'bullet') {
                if (listType !== 'ul') {
                    flushList();
                    listType = 'ul';
                }
                const escapedLabel = escapeHtml(item.label || '');
                const escapedContent = escapeHtml(item.content || '');
                const bulletText = item.label 
                    ? `<strong>${escapedLabel}:</strong> ${escapedContent}`
                    : escapedContent;
                listBuffer.push(bulletText);
            } else if (item.type === 'text' && item.content.trim()) {
                flushList();
                output.push(`<p>${applyInlineFormatting(item.content)}</p>`);
                // Add paragraph break after intro text before bullets start
                if (index === 0 && globalBullets.some(b => b.type === 'bullet')) {
                    pushParagraphBreak();
                }
            }
        });
        flushList();
        return output.join('');
    }
    
    // If no bullets, return original content with inline formatting
    return applyInlineFormatting(content);
}

// Test cases
const tests = [
    {
        name: "Actual LLM output format (3 bullets)",
        input: "The Software License Agreement (SLA) between Mindbody, Inc. (Licensee) and CloudApps Ltd. (Licensor) is effective from May 15, 2023. Key points include:- **License Grant**: The Licensee receives a non-exclusive, non-transferable license to use the software. - **Restrictions**: The Licensee is prohibited from reverse engineering or modifying the software. - **Support**: The Licensor will offer updates and technical support throughout the term.",
        expectedBullets: 3,
        expectedOutput: "ul class=\"message-list\""
    },
    {
        name: "Actual LLM output format (4 bullets)",
        input: "The Software License Agreement (SLA) between Mindbody, Inc. (Licensee) and CloudApps Ltd. (Licensor) is effective from May 15, 2023. Key points include:- **License Grant**: The Licensee receives a non-exclusive, non-transferable license to use the software. - **Restrictions**: The Licensee is prohibited from reverse engineering or modifying the software. - **Support**: The Licensor will offer updates and technical support throughout the term. - **Term & Renewal**: The agreement has an initial term of one year and will automatically renew unless terminated with a thirty-day written notice.",
        expectedBullets: 4,
        expectedOutput: "ul class=\"message-list\""
    },
    {
        name: "Multiple bullets with intro text",
        input: "Summary of the contract:- **Term**: One year. - **Renewal**: Automatic.",
        expectedBullets: 2,
        expectedOutput: "ul class=\"message-list\""
    },
    {
        name: "Single bullet",
        input: "The agreement includes:- **Confidentiality**: All information must be kept confidential.",
        expectedBullets: 1,
        expectedOutput: "ul class=\"message-list\""
    }
];

// Run tests
let passed = 0;
let failed = 0;

console.log("Running frontend formatting tests...\n");

tests.forEach((test, idx) => {
    console.log(`Test ${idx + 1}: ${test.name}`);
    console.log(`Input: ${test.input.substring(0, 80)}...`);
    
    const result = formatMessageContent(test.input);
    
    // Count bullets in output
    const bulletMatches = result.match(/<li>/g);
    const bulletCount = bulletMatches ? bulletMatches.length : 0;
    
    // Check if it contains expected output structure
    const hasList = result.includes(test.expectedOutput);
    
    console.log(`Output length: ${result.length}`);
    console.log(`Bullets found in HTML: ${bulletCount}`);
    console.log(`Has list structure: ${hasList}`);
    console.log(`First 200 chars: ${result.substring(0, 200)}`);
    
    if (bulletCount !== test.expectedBullets) {
        console.log(`❌ FAILED: Found ${bulletCount} bullets, expected ${test.expectedBullets}`);
        failed++;
    } else if (!hasList) {
        console.log(`❌ FAILED: Missing list structure`);
        failed++;
    } else {
        console.log(`✅ PASSED`);
        passed++;
    }
    console.log("");
});

console.log(`\nResults: ${passed} passed, ${failed} failed`);

if (failed > 0) {
    process.exit(1);
}

