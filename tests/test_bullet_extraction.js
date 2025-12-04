// Unit tests for bullet extraction function
// Run with: node tests/test_bullet_extraction.js

// Extract bullets function (copied from app.js for testing)
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
            // Find the period that precedes the next bullet
            const nextBulletStart = matches[idx + 1].index;
            const textToNextBullet = text.substring(contentStart, nextBulletStart);
            
            // Find the last period in this range (which should be before the next bullet)
            const lastPeriodIndex = textToNextBullet.lastIndexOf('.');
            if (lastPeriodIndex !== -1) {
                // Extract content up to (but not including) the period
                content = text.substring(contentStart, contentStart + lastPeriodIndex).trim();
            } else {
                // No period found, extract up to next bullet start
                content = text.substring(contentStart, nextBulletStart).trim();
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

// Test cases
const tests = [
    {
        name: "Markdown format with colon-dash",
        input: "The contract includes:- **License Grant**: The Licensee receives a non-exclusive license. - **Restrictions**: The Licensee is prohibited from reverse engineering.",
        expectedBullets: 2,
        expectedLabels: ["License Grant", "Restrictions"]
    },
    {
        name: "Markdown format without colon",
        input: "Key points:\n- **License Grant**: The Licensee receives a non-exclusive license.\n- **Restrictions**: The Licensee is prohibited from reverse engineering.",
        expectedBullets: 2,
        expectedLabels: ["License Grant", "Restrictions"]
    },
    {
        name: "Inline markdown format (actual LLM output)",
        input: "The Software License Agreement (SLA) between Mindbody, Inc. (Licensee) and CloudApps Ltd. (Licensor) is effective from May 15, 2023. Key points include:- **License Grant**: The Licensee receives a non-exclusive, non-transferable license to use the software. - **Restrictions**: The Licensee is prohibited from reverse engineering or modifying the software. - **Support**: The Licensor will offer updates and technical support throughout the term.",
        expectedBullets: 3,
        expectedLabels: ["License Grant", "Restrictions", "Support"]
    },
    {
        name: "Standard format without markdown",
        input: "The contract includes: - License Grant: The Licensee receives a non-exclusive license. - Restrictions: The Licensee is prohibited from reverse engineering.",
        expectedBullets: 2,
        expectedLabels: ["License Grant", "Restrictions"]
    },
    {
        name: "Mixed format",
        input: "Summary:- **License Grant**: The Licensee receives a non-exclusive license. - **Term**: The agreement lasts for one year.",
        expectedBullets: 2,
        expectedLabels: ["License Grant", "Term"]
    }
];

// Run tests
let passed = 0;
let failed = 0;

console.log("Running bullet extraction tests...\n");

tests.forEach((test, idx) => {
    console.log(`Test ${idx + 1}: ${test.name}`);
    console.log(`Input: ${test.input.substring(0, 100)}...`);
    
    const result = extractBullets(test.input);
    
    if (!result) {
        console.log(`❌ FAILED: No bullets found, expected ${test.expectedBullets}`);
        failed++;
        console.log("");
        return;
    }
    
    const bulletItems = result.filter(item => item.type === 'bullet');
    const labels = bulletItems.map(item => item.label);
    
    if (bulletItems.length !== test.expectedBullets) {
        console.log(`❌ FAILED: Found ${bulletItems.length} bullets, expected ${test.expectedBullets}`);
        console.log(`   Found labels: ${labels.join(", ")}`);
        failed++;
    } else if (!test.expectedLabels.every(label => labels.includes(label))) {
        console.log(`❌ FAILED: Missing expected labels`);
        console.log(`   Expected: ${test.expectedLabels.join(", ")}`);
        console.log(`   Found: ${labels.join(", ")}`);
        failed++;
    } else {
        console.log(`✅ PASSED: Found ${bulletItems.length} bullets with correct labels`);
        passed++;
    }
    console.log("");
});

console.log(`\nResults: ${passed} passed, ${failed} failed`);

if (failed > 0) {
    process.exit(1);
}

