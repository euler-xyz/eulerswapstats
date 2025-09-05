// ==================== Configuration ====================
const CONFIG = {
    V2_API: 'https://index-dev.eul.dev/v2/swap/pools',
    GRAPHQL_API: 'https://index-dev.euler.finance/graphql',
    RPC_URL: 'https://ethereum.publicnode.com',
    KNOWN_DECIMALS: {
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6, // USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7': 6, // USDT
        '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': 8, // WBTC
    },
    KNOWN_SYMBOLS: {
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 'USDC',
        '0xdac17f958d2ee523a2206206994597c13d831ec7': 'USDT',
        '0xc02aaa39b223fc46d80f1ecd791860909c726e2': 'WETH',
        '0x83f20f44975d03b1b09e64809b757c47f942beea': 'sDAI',
        '0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0': 'wstETH',
    },
    STABLECOINS: [
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', // USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7', // USDT
        '0x6b175474e89094c44da98b954eedeac495271d0f', // DAI
        '0x4fabb145d64652a948d72533023f6e7a623c7c53', // BUSD
        '0x8e870d67f660d95d5be530380d0ec0bd388289e1', // USDP
        '0x056fd409e1d7a124bd7017459dfea2f387b6d5cd', // GUSD
        '0x0000000000085d4780b73119b644ae5ecd22b376', // TUSD
        '0x4691937a7508860f876c9c0a2a617e7d9e945d4b', // USDe
        '0x8292bb45bf1ee4d140127049757c2e0ff06317ed', // RLUSD
    ]
};

// ==================== State Management ====================
let state = {
    currentData: null,
    navChart: null,
    compositionChart: null,
    returnsChart: null,
    volumeChart: null,
    drawdownChart: null,
    apiLogs: []
};

// ==================== Initialization ====================
window.addEventListener('DOMContentLoaded', () => {
    // Check if running from file:// and show warning
    if (window.location.protocol === 'file:') {
        document.getElementById('corsNotice').style.display = 'block';
    }
    
    // Set up event listeners
    document.getElementById('poolAddress').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchPoolDataClient();
    });
    
    // Load pool summaries on page load
    loadPoolSummaries();
});

// ==================== Main Client-Side Fetch ====================
async function fetchPoolDataClient() {
    const poolAddress = document.getElementById('poolAddress').value.trim();
    const days = parseInt(document.getElementById('days').value) || 30;
    
    if (!poolAddress || !poolAddress.startsWith('0x') || poolAddress.length !== 42) {
        showError('Please enter a valid pool address');
        return;
    }
    
    showLoading(true);
    hideError();
    state.currentData = null;
    state.apiLogs = [];
    document.getElementById('terminalOutput').innerHTML = '';
    
    try {
        updateStatus('Fetching current pool data...');
        
        // Fetch current pool data from V2 API
        const currentPoolData = await fetchCurrentPoolData(poolAddress);
        
        if (!currentPoolData) {
            throw new Error('Pool not found');
        }
        
        updateStatus('Fetching historical data...');
        
        // Fetch historical data
        const historicalData = await fetchHistoricalData(poolAddress, currentPoolData, days);
        
        // Calculate summary statistics
        const latestNav = historicalData[historicalData.length - 1]?.nav || 0;
        const firstNav = historicalData[0]?.nav || latestNav;
        const navChange = latestNav - firstNav;
        const navAPR = firstNav > 0 ? (navChange / firstNav) * (365 / days) * 100 : 0;
        
        // Get token symbols
        const token0 = currentPoolData.vault0?.asset || currentPoolData.asset0;
        const token1 = currentPoolData.vault1?.asset || currentPoolData.asset1;
        const token0Symbol = await getTokenSymbol(token0);
        const token1Symbol = await getTokenSymbol(token1);
        const tokens = `${token0Symbol}/${token1Symbol}`;
        
        // Send summary to server
        await sendPoolSummary({
            address: poolAddress,
            tokens: tokens,
            nav: latestNav,
            nav_apr: navAPR
        });
        
        // Display results
        state.currentData = {
            pool: currentPoolData,
            historical: historicalData
        };
        
        displayResults(state.currentData);
        
        // Reload pool summaries to show updated list
        loadPoolSummaries();
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'Failed to fetch pool data');
    } finally {
        showLoading(false);
    }
}

// ==================== Send Summary to Server ====================
async function sendPoolSummary(summary) {
    try {
        const response = await fetch('/api/pool-summary', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(summary)
        });
        
        if (!response.ok) {
            console.error('Failed to save pool summary');
        } else {
            logToTerminal(`Pool summary saved to server`, 'success');
        }
    } catch (error) {
        console.error('Error saving pool summary:', error);
    }
}

// ==================== Load Pool Summaries ====================
async function loadPoolSummaries() {
    try {
        const response = await fetch('/api/pool-summaries');
        if (!response.ok) return;
        
        const summaries = await response.json();
        
        // Display summaries in a table
        displayPoolSummaries(summaries);
        
    } catch (error) {
        console.error('Error loading pool summaries:', error);
    }
}

function displayPoolSummaries(summaries) {
    const summariesDiv = document.getElementById('poolSummaries');
    if (!summariesDiv || summaries.length === 0) return;
    
    let html = `
        <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin: 20px 0;">
            <h3 style="margin: 0 0 15px 0;">Recently Analyzed Pools</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid #dee2e6;">
                        <th style="text-align: left; padding: 8px;">Pool</th>
                        <th style="text-align: left; padding: 8px;">Tokens</th>
                        <th style="text-align: right; padding: 8px;">NAV</th>
                        <th style="text-align: right; padding: 8px;">NAV APR</th>
                        <th style="text-align: center; padding: 8px;">Action</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    for (const summary of summaries) {
        const shortAddress = summary.address.substring(0, 6) + '...' + summary.address.substring(38);
        html += `
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 8px; font-family: monospace; font-size: 12px;">${shortAddress}</td>
                <td style="padding: 8px;">${summary.tokens}</td>
                <td style="text-align: right; padding: 8px;">${summary.nav.toFixed(4)}</td>
                <td style="text-align: right; padding: 8px; color: ${summary.nav_apr >= 0 ? '#10b981' : '#ef4444'};">
                    ${summary.nav_apr >= 0 ? '+' : ''}${summary.nav_apr.toFixed(2)}%
                </td>
                <td style="text-align: center; padding: 8px;">
                    <button onclick="loadPool('${summary.address}')" style="padding: 4px 8px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        Load
                    </button>
                </td>
            </tr>
        `;
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    summariesDiv.innerHTML = html;
    summariesDiv.style.display = 'block';
}

function loadPool(address) {
    document.getElementById('poolAddress').value = address;
    fetchPoolDataClient();
}

// ==================== Copy existing helper functions ====================
// (Include all the other functions from app.js that are needed: 
//  fetchCurrentPoolData, fetchHistoricalData, fetchPoolDataAtBlock,
//  fetchSwapVolumes, getTokenSymbol, getTokenDecimals, etc.)

// For now, let me import the key functions we need...</content>
</invoke>