/**
 * Pandora's Box - Frontend Application
 * Real-time WebSocket connection for multi-device sync
 */

// Configuration
// Resolve backend from current host so /app and /app/crypto always hit the same deployment.
const IS_HTTPS = window.location.protocol === 'https:';
const WS_URL = `${IS_HTTPS ? 'wss' : 'ws'}://${window.location.host}/ws`;
const API_URL = `${window.location.origin}/api`;
const API_KEY = 'rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk';

function authHeaders(extraHeaders = {}) {
    return { 'Content-Type': 'application/json', 'X-API-Key': API_KEY, ...extraHeaders };
}

const BIAS_COLORS = {
    TORO_MAJOR: { bg: '#0a2e1a', accent: '#00e676', text: '#00e676' },
    TORO_MINOR: { bg: '#1a2e1a', accent: '#66bb6a', text: '#66bb6a' },
    NEUTRAL:    { bg: '#1a2228', accent: '#78909c', text: '#78909c' },
    URSA_MINOR: { bg: '#2e1a0a', accent: '#ff9800', text: '#ff9800' },
    URSA_MAJOR: { bg: '#2e0a0a', accent: '#e5370e', text: '#e5370e' },
};

const CONFIDENCE_COLORS = {
    HIGH: '#00e676',
    MEDIUM: '#ff9800',
    LOW: '#e5370e',
};

const COMPOSITE_FACTOR_DISPLAY_ORDER = [
    // Intraday (5)
    'vix_term',
    'tick_breadth',
    'spy_trend_intraday',
    'breadth_intraday',
    'gex',
    // Swing (6)
    'credit_spreads',
    'market_breadth',
    'sector_rotation',
    'spy_200sma_distance',
    'iv_regime',
    'mcclellan_oscillator',
    // Macro (8)
    'yield_curve',
    'initial_claims',
    'sahm_rule',
    'copper_gold_ratio',
    'dxy_trend',
    'excess_cape',
    'ism_manufacturing',
    'savita'
];

// --- Daily Quote System ---
const DAILY_QUOTES = {
    greedy: [
        ["Be fearful when others are greedy and greedy only when others are fearful.", "Warren Buffett"],
        ["Bull markets are born on pessimism, grow on skepticism, mature on optimism, and die on euphoria.", "John Templeton"],
        ["The most common cause of low prices is pessimism... It\u2019s optimism that is the enemy of the rational buyer.", "Warren Buffett"],
        ["They know that overstaying the festivities... will eventually bring on pumpkins and mice.", "Warren Buffett"],
        ["There\u2019s a problem, though: They are dancing in a room in which the clocks have no hands.", "Warren Buffett"],
        ["When I see a bubble forming, I rush in to buy, adding fuel to the fire.", "George Soros"],
        ["Three things ruin people: drugs, liquor, and leverage.", "Charlie Munger"],
        ["The game of speculation is the most uniformly fascinating game in the world.", "Jesse Livermore"],
        ["Greed, for lack of a better word, is good.", "Gordon Gekko"],
        ["Greed is all right, by the way. I think greed is healthy.", "Ivan Boesky"],
        ["The four most dangerous words in investing are: \u2018This time it\u2019s different.\u2019", "John Templeton"],
        ["Only when the tide goes out do you discover who\u2019s been swimming naked.", "Warren Buffett"],
        ["There is nothing new in Wall Street. There can\u2019t be because speculation is as old as the hills.", "Jesse Livermore"],
        ["Markets are constantly in a state of uncertainty and flux and money is made by discounting the obvious and betting on the unexpected.", "George Soros"],
        ["When beggars and shoeshine boys can tell you how to get rich, it is time to remind yourself that there is no more dangerous illusion than the belief that one can get something for nothing.", "Bernard Baruch"],
        ["People calculate too much and think too little.", "Charlie Munger"],
        ["It is not the strong who survive, but those who can manage change.", "Leon C. Megginson"],
        ["Don\u2019t be a hero. Don\u2019t have an ego.", "Paul Tudor Jones"],
        ["The idea of caring that someone is making money faster than you is one of the deadly sins.", "Charlie Munger"],
        ["What the wise man does in the beginning, the fool does in the end.", "Howard Marks"],
        ["The three stages of a bull market are the first, when only a few unusually perceptive people believe things will get better; the second, when most investors realize improvement is taking place; and the third, when everyone concludes things will get better forever.", "Howard Marks"],
        ["You adapt, evolve, compete or die.", "Paul Tudor Jones"],
        ["The problem with experts is that they do not know what they do not know.", "Nassim Nicholas Taleb"],
        ["People overvalue their knowledge and underestimate the probability of their being wrong.", "Nassim Nicholas Taleb"],
        ["For investors as a whole, returns decrease as motion increases.", "Warren Buffett"],
        ["The stock market is a device for transferring money from the impatient to the patient.", "Warren Buffett"],
        ["If you don\u2019t know who you are, this is an expensive place to find out.", "Adam Smith"],
        ["The market can stay irrational longer than you can stay solvent.", "John Maynard Keynes"],
        ["What counts for most people in investing is not how much they know, but rather how realistically they define what they don\u2019t know.", "Warren Buffett"],
        ["It never was my thinking that made the big money for me. It always was my sitting.", "Jesse Livermore"],
        ["The big money is not in the buying and selling, but in the waiting.", "Charlie Munger"],
        ["You have to learn how to use your emotions to think, not think with your emotions.", "Robert Kiyosaki"],
        ["The trend is your friend until the end when it bends.", "Ed Seykota"],
        ["Risk means more things can happen than will happen.", "Elroy Dimson"],
        ["Far more money has been lost by investors preparing for corrections than in corrections themselves.", "Peter Lynch"],
        ["Successful speculation requires capital, courage and judgment.", "Philip Carret"],
        ["Nothing sedates rationality like large doses of effortless money.", "Warren Buffett"],
        ["Some people seem to like to lose, so they win by losing money.", "Ed Seykota"],
        ["Never ask a barber if you need a haircut.", "Warren Buffett"],
        ["If you buy them cheap enough, they watch themselves.", "Philip Carret"]
    ],
    optimistic: [
        ["Never bet against America.", "Warren Buffett"],
        ["An investment in knowledge pays the best interest.", "Benjamin Franklin"],
        ["Our favorite holding period is forever.", "Warren Buffett"],
        ["Don\u2019t look for the needle in the haystack. Just buy the haystack!", "John Bogle"],
        ["The time of maximum pessimism is the best time to buy.", "John Templeton"],
        ["Corporate profits will be a lot higher 10 years from now. They\u2019ll be a lot higher 20 years from now.", "Peter Lynch"],
        ["The stock market is filled with individuals who know the price of everything, but the value of nothing.", "Philip Fisher"],
        ["I\u2019m an optimist, both as a person and an investor.", "Philip Carret"],
        ["If you aren\u2019t willing to own a stock for ten years, don\u2019t even think about owning it for ten minutes.", "Warren Buffett"],
        ["The best chance to deploy capital is when things are going down.", "Warren Buffett"],
        ["Wide diversification is only required when investors do not understand what they are doing.", "Warren Buffett"],
        ["Opportunities come infrequently. When it rains gold, put out the bucket, not the thimble.", "Warren Buffett"],
        ["It\u2019s an opportunity to buy more.", "John Bogle"],
        ["The courage to press on regardless... is the quintessential attribute of the successful investor.", "John Bogle"],
        ["Given a 10% chance of a 100 times payoff, you should take that bet every time.", "Jeff Bezos"],
        ["With a good perspective on history, we can have a better understanding of the past and present, and thus a clear vision of the future.", "Carlos Slim Helu"],
        ["Courage taught me no matter how bad a crisis gets... any sound investment will eventually pay off.", "Carlos Slim Helu"],
        ["The stock market is a no-called-strike game. You don\u2019t have to swing at everything\u2014you can wait for your pitch.", "Warren Buffett"],
        ["The best thing to do is to own the S&P 500 index fund.", "Warren Buffett"],
        ["If you invested in a very low-cost index fund... you\u2019ll do better than 90% of people who start investing at the same time.", "Warren Buffett"],
        ["Buy into a company because you want to own it, not because you want the stock to go up.", "Warren Buffett"],
        ["The best thing that happens to us is when a great company gets into temporary trouble.", "Warren Buffett"],
        ["Time is the friend of the wonderful company, the enemy of the mediocre.", "Warren Buffett"],
        ["The stock market is designed to transfer money from the active to the patient.", "Warren Buffett"],
        ["In the short run, the market is a voting machine but in the long run it is a weighing machine.", "Benjamin Graham"],
        ["Invest for the long haul. Don\u2019t get too greedy and don\u2019t get too scared.", "Shelby M.C. Davis"],
        ["I make no attempt to forecast the general market\u2014my efforts are devoted to finding undervalued securities.", "Warren Buffett"],
        ["The most important quality for an investor is temperament, not intellect.", "Warren Buffett"],
        ["Behind every stock is a company. Find out what it\u2019s doing.", "Peter Lynch"],
        ["Know what you own, and know why you own it.", "Peter Lynch"],
        ["To the extent we have been successful, it is because we concentrated on identifying one-foot hurdles that we could step over.", "Warren Buffett"],
        ["Traders rarely die rich, patient investors often do.", "Philip Carret"],
        ["All intelligent investing is value investing\u2014acquiring more than you are paying for.", "Charlie Munger"],
        ["The best way to own common stocks is through an index fund.", "John Bogle"],
        ["Finding the really outstanding companies and staying with them through all the fluctuations of a gyrating market proved far more profitable than trying to buy them cheap and sell them dear.", "Philip A. Fisher"],
        ["The great thing about the stock market is that it is the only place where things go on sale and all the customers run out of the store.", "Cullen Roche"],
        ["Buy when everyone else is selling and hold when everyone else is buying.", "J. Paul Getty"],
        ["To invest successfully over a lifetime does not require a stratospheric IQ, unusual business insights, or inside information.", "Warren Buffett"],
        ["A low-cost index fund is the most sensible equity investment for the great majority of investors.", "John Bogle"],
        ["Stay the course.", "John Bogle"]
    ],
    pragmatic: [
        ["Price is what you pay; value is what you get.", "Warren Buffett"],
        ["Risk comes from not knowing what you\u2019re doing.", "Warren Buffett"],
        ["The essence of investment management is the management of risks, not the management of returns.", "Benjamin Graham"],
        ["Investment is most intelligent when it is most businesslike.", "Benjamin Graham"],
        ["The individual investor should act consistently as an investor and not as a speculator.", "Benjamin Graham"],
        ["In the world of money, which is a world shaped by human behavior, nobody has the foggiest notion of what will happen in the future.", "John Kenneth Galbraith"],
        ["Most of the time we are punished if we go against the trend. Only at an inflection point are we rewarded.", "George Soros"],
        ["It\u2019s not whether you\u2019re right or wrong that\u2019s important, but how much money you make when you\u2019re right and how much you lose when you\u2019re wrong.", "George Soros"],
        ["My approach works not by making valid predictions, but by allowing me to correct false ones.", "George Soros"],
        ["Trade only when the market is clearly bullish or bearish.", "Jesse Livermore"],
        ["There are many times when I have been completely in cash.", "Jesse Livermore"],
        ["The change in the major trend is what hurts most speculators.", "Jesse Livermore"],
        ["Don\u2019t be a hero. Don\u2019t have an ego. Always question yourself and your ability.", "Paul Tudor Jones"],
        ["The most important rule of trading is to play great defense, not great offense.", "Paul Tudor Jones"],
        ["Losers average losers.", "Paul Tudor Jones"],
        ["If you have a losing position that is making you uncomfortable, the solution is very simple: get out.", "Paul Tudor Jones"],
        ["Cut your losses.", "George Soros"],
        ["The investor\u2019s chief problem\u2014and even his worst enemy\u2014is likely to be himself.", "Benjamin Graham"],
        ["I react pragmatically. Where the market works, I\u2019m for that. Where the government is necessary, I\u2019m for that.", "John Kenneth Galbraith"],
        ["It will fluctuate.", "J. P. Morgan"],
        ["Inflation is always and everywhere a monetary phenomenon.", "Milton Friedman"],
        ["Economics is not simply a topic on which to express opinions or vent emotions.", "Thomas Sowell"],
        ["Everyone responds to incentives, including people you want to help.", "Thomas Sowell"],
        ["Many things that are desirable are not feasible.", "Thomas Sowell"],
        ["Other people have more information about their abilities, their efforts, and their preferences than you do.", "Thomas Sowell"],
        ["The market is there to serve you, not to instruct you.", "Benjamin Graham"],
        ["Basically, price fluctuations have only one significant meaning for the true investor.", "Benjamin Graham"],
        ["At other times he will do better if he forgets about the stock market and pays attention to his dividend returns and to the operating results of his companies.", "Benjamin Graham"],
        ["The principal role of the mutual fund is to serve its investors.", "John Bogle"],
        ["Beating the market is a zero-sum game for investors.", "John Bogle"],
        ["The zero-sum game before costs becomes a loser\u2019s game after costs.", "John Bogle"],
        ["Stock prices will always be far more volatile than cash-equivalent holdings.", "Warren Buffett"],
        ["Volatility is far from synonymous with risk.", "Warren Buffett"],
        ["We have no theory of the duration of a bubble. It can always go on longer than anyone expects.", "Paul Samuelson"],
        ["The real reason that physicians are mediocre investors is that it never occurs to them that finance is a science.", "William J. Bernstein"],
        ["A healthy portfolio requires a regular checkup\u2014perhaps every six months or so.", "Peter Lynch"],
        ["The most important thing in investing is to use common sense.", "Philip Carret"],
        ["If you don\u2019t understand a company, if you can\u2019t explain it to a ten-year-old in two minutes or less, don\u2019t own it.", "Peter Lynch"],
        ["You get recessions, you have stock market declines. If you don\u2019t understand that\u2019s going to happen, then you\u2019re not ready.", "Peter Lynch"],
        ["A speculator is a man who observes the future, and acts before it occurs.", "Bernard Baruch"]
    ],
    cynical: [
        ["The function of economic forecasting is to make astrology look respectable.", "John Kenneth Galbraith"],
        ["There are two kinds of forecasters: those who don\u2019t know, and those who don\u2019t know they don\u2019t know.", "John Kenneth Galbraith"],
        ["The stock market has forecast nine of the last five recessions.", "Paul Samuelson"],
        ["The world of finance is a mysterious world in which, incredible as the fact may appear, evaporation precedes liquidation.", "Joseph Conrad"],
        ["FINANCE, n. The art or science of managing revenues and resources for the best advantage of the manager.", "Ambrose Bierce"],
        ["ECONOMY, n. Purchasing the barrel of whiskey that you do not need for the price of the cow that you cannot afford.", "Ambrose Bierce"],
        ["We have met the enemy and he is us.", "John Bogle"],
        ["The business model of Wall Street is fraud.", "Bernie Sanders"],
        ["Wall Street regulates the Congress.", "Bernie Sanders"],
        ["The U.S. brokerage and investment banking industry has transformed the modern American stock market into nothing more than a mechanism for transferring wealth from shareholders to management.", "Peter Schiff"],
        ["The dumbest reason in the world to buy a stock is because it\u2019s going up.", "Warren Buffett"],
        ["Forecasts may tell you a great deal about the forecaster; they tell you nothing about the future.", "Warren Buffett"],
        ["We\u2019ve long felt that the only value of stock forecasters is to make fortune tellers look good.", "Warren Buffett"],
        ["Nothing in finance is more fatuous and harmful... than the attitude: \u2018If you don\u2019t like the management, sell your stock.\u2019", "Benjamin Graham"],
        ["The rich are always advising the poor, but the poor do not get much benefit from their advice.", "John Selden"],
        ["The public owners seem to have abdicated all claim to control over the paid superintendents of their property.", "Benjamin Graham"],
        ["If past history was all there was to the game, the richest people would be librarians.", "Warren Buffett"],
        ["It is difficult to get a man to understand something when his salary depends upon his not understanding it.", "Upton Sinclair"],
        ["The whole notion of the free market... is a very thin rationale for unmitigated greed by a tiny oligarchic elite.", "Chris Hedges"],
        ["When people behave badly they always invent a philosophy of life which represents their bad actions... as results of unalterable laws beyond their control.", "Leo Tolstoy"],
        ["Capitalism is the astonishing belief that the nastiest motives of the nastiest men somehow or other work together for the best results.", "John Maynard Keynes"],
        ["Wealth, in even the most improbable cases, manages to convey the aspect of intelligence.", "John Kenneth Galbraith"],
        ["Politics is not the art of the possible. It consists in choosing between the disastrous and the unpalatable.", "John Kenneth Galbraith"],
        ["There\u2019s no longer any reason to believe that the wizards of Wall Street actually contribute anything positive to society.", "Paul Krugman"],
        ["It\u2019s hard to think of any major recent financial innovations that actually aided society, as opposed to being new, improved ways to blow bubbles.", "Paul Krugman"],
        ["The U.S. stock market was now a class system, rooted in speed, of haves and have-nots.", "Michael Lewis"],
        ["What had once been the world\u2019s most public, most democratic financial market had become... a private viewing of a stolen work of art.", "Michael Lewis"],
        ["Money never sleeps.", "Gordon Gekko"],
        ["The problem with money... it makes you do things you don\u2019t want to do.", "Lou Mannheim"],
        ["Kid, you\u2019re on a roll. Enjoy it while it lasts, because it never does.", "Lou Mannheim"],
        ["No such thing except death and taxes.", "Lou Mannheim"],
        ["Quick-buck artists come and go with every bull market, but the steady players make it through the bear market.", "Lou Mannheim"],
        ["It\u2019s a zero-sum game\u2014somebody wins, somebody loses.", "Gordon Gekko"],
        ["I create nothing. I own.", "Gordon Gekko"],
        ["We make the rules, pal.", "Gordon Gekko"],
        ["The main purpose of the stock market is to make fools of as many men as possible.", "Bernard Baruch"],
        ["Markets don\u2019t look after social needs.", "George Soros"],
        ["Markets are designed to allow individuals to look after their private needs and to pursue profit.", "George Soros"],
        ["I have already made up my mind, don\u2019t confuse me with facts.", "Philip A. Fisher"],
        ["I can hire one half of the working class to kill the other half.", "Jay Gould"]
    ],
    pessimistic: [
        ["Many of the greatest economic evils of our time are the fruits of risk, uncertainty, and ignorance.", "John Maynard Keynes"],
        ["Bottoms in the investment world don\u2019t end with four-year lows; they end with 10- or 15-year lows.", "Jim Rogers"],
        ["I haven\u2019t the faintest idea where the stock market is going. But I can promise you that someday there will be a big bear market\u2014and a lot of people will lose money.", "Philip Carret"],
        ["I can calculate the movement of the stars, but not the madness of men.", "Isaac Newton"],
        ["It was one of those rare manifestations of mass financial madness.", "Benjamin Graham"],
        ["That man would be better off if his stocks had no market quotation at all.", "Benjamin Graham"],
        ["The debt crisis is not a temporary problem, it is a structural one. We need rehab.", "Nassim Nicholas Taleb"],
        ["Economic life should be definancialised.", "Nassim Nicholas Taleb"],
        ["Markets do not harbour the certainties that normal citizens require.", "Nassim Nicholas Taleb"],
        ["Prices are too high is far from synonymous with the next move will be downward.", "Howard Marks"],
        ["You only learn who has been swimming naked when the tide goes out.", "Warren Buffett"],
        ["In bear markets, things first decline to reasonable prices, then they fall to cheap prices, and then they reach unbelievable giveaway prices.", "Jim Rogers"],
        ["After that, things get really bad, and everybody gets cleaned out.", "Jim Rogers"],
        ["If the market persists in behaving foolishly, all he seems to need is ordinary common sense in order to exploit its foolishness.", "Benjamin Graham"],
        ["Not all bubbles involve the extension of credit; some are based on equity leveraging.", "George Soros"],
        ["Equilibrium itself has rarely been observed in real life\u2014market prices have a notorious habit of fluctuating.", "George Soros"],
        ["The usual way I lose money is by buying concept stocks.", "Philip Carret"],
        ["The investors operate with limited intelligence: they do not know everything.", "George Soros"],
        ["The nature of unemployment today is totally different from what it was a year ago.", "John Maynard Keynes"],
        ["Capitalism, wisely managed, can probably be made more efficient... but in itself it is in many ways extremely objectionable.", "John Maynard Keynes"],
        ["The pre-1800 pattern of commercial panics had to be a case of non macro-efficiency of markets.", "Paul Samuelson"],
        ["You cannot make money on correcting macro inefficiencies in the price level of the stock market.", "Paul Samuelson"],
        ["We have no theory of the duration of a bubble.", "Paul Samuelson"],
        ["The future can well witness the oldest business cycle mechanism, the South Sea Bubble, and that kind of thing.", "Paul Samuelson"],
        ["There are old investors, and there are bold investors, but there are no old bold investors.", "Howard Marks"],
        ["The world is not driven by greed. It\u2019s driven by envy.", "Charlie Munger"],
        ["Envy is a really stupid sin because it\u2019s the only one you could never possibly have any fun at.", "Charlie Munger"],
        ["When everybody thinks alike, everybody is likely to be wrong.", "Humphrey B. Neill"],
        ["If you\u2019re in the poker game and you don\u2019t know who the patsy is, you\u2019re the patsy.", "Warren Buffett"],
        ["There are old traders and there are bold traders, but there are very few old, bold traders.", "Wall Street saying"],
        ["The first rule is not to lose. The second rule is not to forget the first rule.", "Warren Buffett"],
        ["You can be certain that the market will eventually return to value.", "Benjamin Graham"],
        ["History never looks like history when you are living through it.", "John W. Gardner"],
        ["For every action, there is an equal and opposite government program.", "Bob Wells"],
        ["Speculation is most dangerous when it looks easiest.", "Howard Marks"],
        ["Investing is a popularity contest, and the most dangerous thing is to buy something at the peak of its popularity.", "Howard Marks"],
        ["Skepticism and pessimism aren\u2019t synonymous. Skepticism calls for pessimism when optimism is excessive.", "Howard Marks"],
        ["Bullish or bearish are terms used by people who do not engage in practicing uncertainty.", "Nassim Nicholas Taleb"],
        ["The more the market goes up, the lower the prospective return.", "Howard Marks"],
        ["This is not a market for the complacent.", "Howard Marks"]
    ]
};

const BIAS_TO_QUOTE_CATEGORY = {
    TORO_MAJOR: 'greedy',
    TORO_MINOR: 'optimistic',
    NEUTRAL: 'pragmatic',
    URSA_MINOR: 'pessimistic',
    URSA_MAJOR: 'cynical'
};

function getDailyQuote(biasLevel) {
    const category = BIAS_TO_QUOTE_CATEGORY[biasLevel] || 'pragmatic';
    const quotes = DAILY_QUOTES[category];
    if (!quotes || quotes.length === 0) return null;

    const storageKey = `dailyQuote_shown_${category}`;
    const dateKey = `dailyQuote_date_${category}`;
    const indexKey = `dailyQuote_index_${category}`;
    const today = new Date().toISOString().slice(0, 10);

    // If we already picked a quote for this category today, reuse it
    const savedDate = localStorage.getItem(dateKey);
    const savedIndex = parseInt(localStorage.getItem(indexKey), 10);
    if (savedDate === today && Number.isFinite(savedIndex) && savedIndex < quotes.length) {
        return { text: quotes[savedIndex][0], author: quotes[savedIndex][1] };
    }

    // Load shown indices for this category
    let shown = [];
    try { shown = JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch (e) { shown = []; }

    // If all shown, reset
    if (shown.length >= quotes.length) shown = [];

    // Build available pool
    const available = [];
    for (let i = 0; i < quotes.length; i++) {
        if (!shown.includes(i)) available.push(i);
    }

    // Deterministic daily pick from available pool using date as seed
    const dateSeed = today.split('-').join('');
    const hash = Array.from(dateSeed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
    const pick = available[Math.abs(hash) % available.length];

    // Save state
    shown.push(pick);
    localStorage.setItem(storageKey, JSON.stringify(shown));
    localStorage.setItem(dateKey, today);
    localStorage.setItem(indexKey, String(pick));

    return { text: quotes[pick][0], author: quotes[pick][1] };
}

function updateDailyQuote(biasLevel) {
    const el = document.getElementById('dailyQuote');
    if (!el) return;
    const quote = getDailyQuote(biasLevel);
    if (!quote) { el.innerHTML = ''; return; }
    const colors = BIAS_COLORS[biasLevel] || BIAS_COLORS.NEUTRAL;
    el.innerHTML = `\u201C${escapeHtml(quote.text)}\u201D <span class="quote-author" style="color:${colors.accent}">\u2014 ${escapeHtml(quote.author)}</span>`;
}

// Direction alignment check — used by WebSocket handlers and position card logic
function isDirectionAligned(posDirection, signalDirection) {
    const pos = (posDirection || '').toUpperCase();
    const sig = (signalDirection || '').toUpperCase();
    const bullish = ['LONG', 'BULLISH', 'BUY'];
    const bearish = ['SHORT', 'BEARISH', 'SELL'];
    return (bullish.includes(pos) && bullish.includes(sig)) ||
           (bearish.includes(pos) && bearish.includes(sig));
}

// Shared helpers
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatChange(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '-';
    const num = Number(value);
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
}

function changeColor(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '#78909c';
    const num = Number(value);
    if (num > 0) return '#4caf50';
    if (num < 0) return '#e5370e';
    return '#78909c';
}

function normalizeRiskReward(value) {
    if (value === null || value === undefined || value === '') return null;
    const num = Number.parseFloat(value);
    if (!Number.isFinite(num)) return null;
    const normalized = Math.abs(num);
    return normalized > 0 ? normalized : null;
}

function formatRiskReward(value) {
    const normalized = normalizeRiskReward(value);
    return normalized ? `${normalized.toFixed(1)}:1` : '-';
}

// State
let ws = null;
let tvWidget = null;
let currentSymbol = 'SPY';
let currentTimeframe = 'WEEKLY';
const APP_MODES = {
    HUB: 'hub',
    CRYPTO: 'crypto',
    ANALYTICS: 'analytics'
};
let signals = {
    equity: [],
    crypto: []
};
const TRADE_IDEAS_PAGE_SIZE = 10;
let tradeIdeasPagination = {
    equity: { offset: 0, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false },
    crypto: { offset: 0, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false }
};

// Price levels to display on chart (entry, stop, target)
let activePriceLevels = null;
let tvLevelShapes = [];

// Weekly Bias Factor State
let weeklyBiasFullData = null; // Stores complete weekly bias data with factors
let weeklyBiasFactorStates = {
    index_trends: true,
    dollar_trend: true,
    sector_rotation: true,
    credit_spreads: true,
    market_breadth: true,
    vix_term_structure: true
};

// Daily Bias Factor State
let dailyBiasFullData = null;
let dailyBiasFactorStates = {
    spy_rsi: true,
    vix_level: true,
    tech_leadership: true,
    small_cap_risk: true,
    spy_trend: true,
    market_breadth: true,
    tick_breadth: true
};

// Composite Bias API response cache (used by crypto bias bar without needing DOM from hub)
let _compositeBiasData = null;
let _dailyBiasPrimaryData = null;

let cryptoMarketData = null;
let cryptoMarketTimer = null;
let cryptoMarketLastGood = {};
let cryptoWma9 = null;
let cryptoWmaUpdated = null;
let cryptoWmaTimer = null;
let cryptoWmaLoading = false;
const CRYPTO_MARKET_POLL_MS = 5 * 1000;

// Cyclical Bias Factor State
let cyclicalBiasFullData = null;
let cyclicalBiasFactorStates = {
    sma_200_positions: true,
    yield_curve: true,
    credit_spreads: true,
    excess_cape_yield: true,
    savita_indicator: true,
    longterm_breadth: true,
    sahm_rule: true
};

// Personal Bias & Override State
let personalBias = 'NEUTRAL';  // NEUTRAL, TORO, URSA
let biasOverrideActive = false;
let biasOverrideDirection = 'MAJOR_TORO';  // MAJOR_TORO or MAJOR_URSA

// Per-timeframe personal bias toggles (default: apply to all)
let personalBiasAppliesTo = {
    daily: true,
    weekly: true,
    cyclical: true
};

let manualPositionContext = 'equity';

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    // Bind critical UI interactions first so mode switches still work
    // even if downstream initializers fail.
    try {
        initRouting();
    } catch (error) {
        console.error('initRouting failed:', error);
    }

    try {
        initEventListeners();
    } catch (error) {
        console.error('initEventListeners failed:', error);
    }

    try {
        initTradingViewWidget();
    } catch (error) {
        console.error('initTradingViewWidget failed:', error);
    }

    try {
        initWebSocket();
    } catch (error) {
        console.error('initWebSocket failed:', error);
    }

    Promise.resolve(loadInitialData()).catch((error) => {
        console.error('loadInitialData failed:', error);
    });

    try {
        initCryptoScalper();
    } catch (error) {
        console.error('initCryptoScalper failed:', error);
    }

    // Portfolio tracker (Brief 07-E)
    try {
        loadPortfolioBalances();
        loadPortfolioPositions();
    } catch (error) {
        console.error('Portfolio load failed:', error);
    }
});

function initRouting() {
    const modeFromPath = getModeFromPath();
    const storedMode = localStorage.getItem('pandoraAppMode');
    const initialMode = modeFromPath || storedMode || APP_MODES.HUB;

    setMode(initialMode, { replace: true });

    window.addEventListener('popstate', () => {
        const nextMode = getModeFromPath() || localStorage.getItem('pandoraAppMode') || APP_MODES.HUB;
        setMode(nextMode, { skipHistory: true });
    });
}

function getModeFromPath() {
    const path = window.location.pathname.replace(/\/$/, '');
    if (path.endsWith('/analytics')) return APP_MODES.ANALYTICS;
    if (path.endsWith('/crypto')) return APP_MODES.CRYPTO;
    if (path.endsWith('/hub')) return APP_MODES.HUB;
    return null;
}

function getModeBasePath() {
    const path = window.location.pathname.replace(/\/$/, '');
    if (path.endsWith('/analytics')) return path.slice(0, -10) || '';
    if (path.endsWith('/crypto')) return path.slice(0, -7) || '';
    if (path.endsWith('/hub')) return path.slice(0, -4) || '';
    return path || '';
}

function buildModePath(mode) {
    const basePath = getModeBasePath();
    const safeBase = basePath === '/' ? '' : basePath;
    return `${safeBase}/${mode}`.replace(/\/+/g, '/');
}

function setMode(mode, options = {}) {
    let nextMode = APP_MODES.HUB;
    if (mode === APP_MODES.CRYPTO) nextMode = APP_MODES.CRYPTO;
    if (mode === APP_MODES.ANALYTICS) nextMode = APP_MODES.ANALYTICS;
    document.body.dataset.mode = nextMode;

    const hubShell = document.getElementById('hubShell');
    const cryptoShell = document.getElementById('cryptoShell');
    const analyticsShell = document.getElementById('analyticsShell');
    if (hubShell) hubShell.hidden = nextMode !== APP_MODES.HUB;
    if (cryptoShell) cryptoShell.hidden = nextMode !== APP_MODES.CRYPTO;
    if (analyticsShell) analyticsShell.hidden = nextMode !== APP_MODES.ANALYTICS;

    const hubBtn = document.getElementById('modeHubBtn');
    const cryptoBtn = document.getElementById('modeCryptoBtn');
    const analyticsBtn = document.getElementById('modeAnalyticsBtn');
    if (hubBtn && cryptoBtn && analyticsBtn) {
        hubBtn.classList.toggle('active', nextMode === APP_MODES.HUB);
        cryptoBtn.classList.toggle('active', nextMode === APP_MODES.CRYPTO);
        analyticsBtn.classList.toggle('active', nextMode === APP_MODES.ANALYTICS);
        hubBtn.setAttribute('aria-selected', nextMode === APP_MODES.HUB);
        cryptoBtn.setAttribute('aria-selected', nextMode === APP_MODES.CRYPTO);
        analyticsBtn.setAttribute('aria-selected', nextMode === APP_MODES.ANALYTICS);
    }

    localStorage.setItem('pandoraAppMode', nextMode);

    if (!options.skipHistory) {
        const targetPath = buildModePath(nextMode);
        const currentPath = window.location.pathname;
        if (currentPath !== targetPath) {
            if (options.replace || currentPath === '/' || currentPath === '') {
                window.history.replaceState({}, '', targetPath);
            } else {
                window.history.pushState({}, '', targetPath);
            }
        }
    }

    renderCryptoSignals();
    renderCryptoBiasSummary();

    // Only poll the crypto market endpoint while the crypto view is active.
    // This keeps the 5s update cadence without burning API calls in Hub mode.
    if (nextMode === APP_MODES.CRYPTO) {
        startCryptoMarketPolling();
    } else {
        stopCryptoMarketPolling();
    }

    // Initialize crypto chart when switching to crypto mode
    if (nextMode === APP_MODES.CRYPTO && !cryptoTvWidget) {
        setTimeout(initCryptoChart, 200);
    }

    try {
        document.dispatchEvent(new CustomEvent('pandora:modechange', { detail: { mode: nextMode } }));
    } catch (error) {
        console.warn('Mode change event dispatch failed:', error);
    }
}

// TradingView Widget
function initTradingViewWidget() {
    const container = document.getElementById('tradingview-widget');
    
    // Clear any existing content
    container.innerHTML = '';
    
    tvWidget = new TradingView.widget({
        symbol: currentSymbol,
        interval: 'D',
        timezone: 'America/New_York',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0a0e27',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        container_id: 'tradingview-widget',
        autosize: true,
        studies: [
            { id: 'MASimple@tv-basicstudies', inputs: { length: 200 } }
        ],
        studies_overrides: {
            // 200 SMA - thick teal line
            'moving average.ma.color': '#14b8a6',
            'moving average.ma.linewidth': 3,
            // Volume bars
            'volume.volume.color.0': '#FF6B35',
            'volume.volume.color.1': '#7CFF6B',
            'volume.volume ma.color': '#14b8a6'
        },
        overrides: {
            // Candlestick colors - lime up, orange down
            'mainSeriesProperties.candleStyle.upColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.downColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.borderUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.borderDownColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.wickUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.wickDownColor': '#FF6B35',
            
            // Background - dark navy
            'paneProperties.background': '#0a0e27',
            'paneProperties.backgroundType': 'solid',
            
            // Grid lines - subtle
            'paneProperties.vertGridProperties.color': '#1e293b',
            'paneProperties.horzGridProperties.color': '#1e293b',
            'paneProperties.vertGridProperties.style': 0,
            'paneProperties.horzGridProperties.style': 0,
            
            // Scale/axis text
            'scalesProperties.textColor': '#94a3b8',
            'scalesProperties.backgroundColor': '#0a0e27',
            'scalesProperties.lineColor': '#334155',
            
            // Crosshair
            'paneProperties.crossHairProperties.color': '#14b8a6',
            'paneProperties.crossHairProperties.style': 0,
            
            // Legend text
            'paneProperties.legendProperties.showStudyArguments': true,
            'paneProperties.legendProperties.showStudyTitles': true,
            'paneProperties.legendProperties.showStudyValues': true,
            'paneProperties.legendProperties.showSeriesTitle': true,
            'paneProperties.legendProperties.showSeriesOHLC': true,
            
            // Separator lines between panes
            'paneProperties.separatorColor': '#334155'
        },
        loading_screen: {
            backgroundColor: '#0a0e27',
            foregroundColor: '#14b8a6'
        }
    });

    // Best-effort: draw levels if the widget supports it
    if (tvWidget && typeof tvWidget.onChartReady === 'function') {
        tvWidget.onChartReady(() => {
            drawLevelsOnChart();
        });
    }
}

function changeChartSymbol(symbol) {
    currentSymbol = symbol;
    
    // Update tab active state
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.symbol === symbol);
    });
    
    // Update price levels panel for this symbol
    updatePriceLevelsPanel(symbol);
    
    // Reinitialize widget with new symbol
    initTradingViewWidget();
}

function getTickerFromSymbol(symbol) {
    if (!symbol) return symbol;
    const upper = symbol.toUpperCase();
    if (upper.endsWith('USDT')) return upper.slice(0, -4);
    if (upper.endsWith('USD')) return upper.slice(0, -3);
    return upper;
}

function updatePriceLevelsPanel(symbol) {
    const panel = document.getElementById('priceLevelsPanel');
    if (!panel) return;
    
    // Check if we have price levels for this symbol
    const tickerKey = getTickerFromSymbol(symbol);
    const levels = window.activePriceLevels?.[tickerKey];
    
    if (levels) {
        // Show panel with levels
        panel.style.display = 'block';
        document.getElementById('priceLevelsTicker').textContent = tickerKey;
        document.getElementById('priceLevelEntry').textContent = levels.entry ? `$${parseFloat(levels.entry).toFixed(2)}` : '--';
        document.getElementById('priceLevelStop').textContent = levels.stop ? `$${parseFloat(levels.stop).toFixed(2)}` : '--';
        document.getElementById('priceLevelTarget1').textContent = levels.target1 ? `$${parseFloat(levels.target1).toFixed(2)}` : '--';
        
        const target2Row = document.getElementById('priceLevelTarget2Row');
        if (levels.target2) {
            document.getElementById('priceLevelTarget2').textContent = `$${parseFloat(levels.target2).toFixed(2)}`;
            target2Row.style.display = 'flex';
        } else {
            target2Row.style.display = 'none';
        }
    } else {
        // Check if there's an open position for this symbol
        const position = openPositions.find(p => (p.ticker || '').toUpperCase() === tickerKey);
        if (position) {
            panel.style.display = 'block';
            document.getElementById('priceLevelsTicker').textContent = tickerKey;
            document.getElementById('priceLevelEntry').textContent = position.entry_price ? `$${parseFloat(position.entry_price).toFixed(2)}` : '--';
            document.getElementById('priceLevelStop').textContent = position.stop_loss ? `$${parseFloat(position.stop_loss).toFixed(2)}` : '--';
            document.getElementById('priceLevelTarget1').textContent = position.target_1 ? `$${parseFloat(position.target_1).toFixed(2)}` : '--';
            
            const target2Row = document.getElementById('priceLevelTarget2Row');
            if (position.target_2) {
                document.getElementById('priceLevelTarget2').textContent = `$${parseFloat(position.target_2).toFixed(2)}`;
                target2Row.style.display = 'flex';
            } else {
                target2Row.style.display = 'none';
            }
        } else {
            // No levels for this symbol - hide panel
            panel.style.display = 'none';
        }
    }

    // Best-effort: update chart lines if supported
    drawLevelsOnChart();
}

function showTradeOnChart(signal) {
    // Change to the signal's ticker
    const symbol = signal.asset_class === 'CRYPTO' 
        ? signal.ticker + 'USD' 
        : signal.ticker;
    
    currentSymbol = symbol;
    
    // Store price levels to display
    storePriceLevels(signal.ticker, {
        entry: signal.entry_price,
        stop: signal.stop_loss,
        target1: signal.target_1,
        target2: signal.target_2
    });
    
    // Update tab styling (remove active from all since this is a custom ticker)
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.symbol === symbol) {
            tab.classList.add('active');
        }
    });
    
    // Reinitialize with the new symbol
    initTradingViewWidget();
    
    // Note: TradingView widget doesn't easily support drawing horizontal lines
    // For full price level display, we'd need TradingView Advanced Charts (paid)
    // For now, the signal details panel shows the levels clearly
    
    console.log(`ðŸ“Š Showing ${signal.ticker} on chart with levels:`, window.activePriceLevels?.[signal.ticker]);
}

function clearChartLevels() {
    if (!tvWidget || typeof tvWidget.activeChart !== 'function') {
        tvLevelShapes = [];
        return;
    }

    try {
        const chart = tvWidget.activeChart();
        if (!chart || typeof chart.removeEntity !== 'function') {
            tvLevelShapes = [];
            return;
        }

        for (const id of tvLevelShapes) {
            try {
                chart.removeEntity(id);
            } catch {
                // ignore best-effort cleanup
            }
        }
    } catch {
        // ignore best-effort cleanup
    }

    tvLevelShapes = [];
}

function drawLevelsOnChart() {
    if (!tvWidget || typeof tvWidget.activeChart !== 'function') {
        return;
    }

    const tickerKey = getTickerFromSymbol(currentSymbol);
    const levels = window.activePriceLevels?.[tickerKey];
    if (!levels) {
        clearChartLevels();
        return;
    }

    try {
        const chart = tvWidget.activeChart();
        if (!chart || typeof chart.createShape !== 'function') {
            return;
        }

        clearChartLevels();

        const shapes = [
            { price: levels.entry, color: '#22c55e', text: 'Entry' },
            { price: levels.stop, color: '#e5370e', text: 'Stop' },
            { price: levels.target1, color: '#3b82f6', text: 'Target' },
            { price: levels.target2, color: '#6366f1', text: 'Target 2' }
        ];

        for (const shape of shapes) {
            if (!shape.price) continue;
            const id = chart.createShape(
                { price: shape.price },
                {
                    shape: 'horizontal_line',
                    text: shape.text,
                    lock: true,
                    disableSelection: true,
                    disableSave: true,
                    overrides: {
                        linecolor: shape.color,
                        linewidth: 2
                    }
                }
            );
            if (id) tvLevelShapes.push(id);
        }
    } catch {
        // Widget may not support drawings; ignore
    }
}

// WebSocket Connection
function initWebSocket() {
    console.log('ðŸ”Œ Connecting to Pandora\'s Box...');
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('âœ… Connected to backend');
        updateConnectionStatus(true);
        
        // Send heartbeat every 30 seconds
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);
    };
    
    ws.onmessage = (event) => {
        // Handle heartbeat pong response
        if (event.data === 'pong') {
            return;
        }
        
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (e) {
            console.warn('âš ï¸ Non-JSON message received:', event.data);
        }
    };
    
    ws.onerror = (error) => {
        console.error('âŒ WebSocket error:', error);
        updateConnectionStatus(false);
    };
    
    ws.onclose = () => {
        console.log('ðŸ”Œ Connection closed. Reconnecting...');
        updateConnectionStatus(false);
        
        // Reconnect after 3 seconds
        setTimeout(initWebSocket, 3000);
    };
}

function handleWebSocketMessage(message) {
    console.log('ðŸ“¨ Received:', message);
    
    switch (message.type) {
        case 'NEW_SIGNAL':
            // Add signal and check if it should jump to top 10
            handleNewSignal(message.data);
            break;
        case 'SIGNAL_PRIORITY_UPDATE':
            // New high-priority signal that should be shown immediately
            handlePrioritySignal(message.data);
            break;
        case 'SIGNAL_ACCEPTED':
            // Signal was accepted by user, remove from feed and refill
            removeSignal(message.signal_id);
            refillTradeIdeas();
            break;
        case 'SIGNAL_DISMISSED':
            // Signal was dismissed, remove from feed
            removeSignal(message.signal_id);
            refillTradeIdeas();
            break;
        case 'BIAS_UPDATE':
            if (message.data && typeof message.data.bias_level !== 'undefined' && typeof message.data.composite_score !== 'undefined') {
                fetchCompositeBias();
                flashCompositeBanner();
            } else {
                // Handle weekly bias updates with factor filtering
                if (message.data.timeframe === 'weekly' || message.data.timeframe === 'WEEKLY') {
                    weeklyBiasFullData = message.data;
                    updateWeeklyBiasWithFactors(message.data);
                } else {
                    updateBias(message.data);
                }
                // bias shift status removed (Phase 0D) — endpoint was dead
            }
            break;
        case 'POSITION_UPDATE':
            updatePosition(message.data);
            break;
        case 'SCOUT_ALERT':
            handleNewSignal(message.data);
            break;
        case 'FLOW_UPDATE':
            // New flow data from Discord bot via UW - refresh the Options Flow section
            console.log(`ðŸ‹ Flow update: ${message.count} tickers (${(message.tickers_updated || []).join(', ')})`);
            loadFlowData();
            checkFlowStatus();
            break;
        case 'circuit_breaker':
            // CB state change (trigger, reset, etc.)
            handleCircuitBreakerUpdate(message.state || message);
            fetchCompositeBias();
            break;
        case 'circuit_breaker_pending_reset':
            // CB decay complete, condition cleared — show accept/reject banner
            handleCircuitBreakerPendingReset(message.state || message);
            break;
    }
}


function handleCircuitBreakerUpdate(state) {
    const banner = document.getElementById('cbPendingResetBanner');
    if (!banner) return;

    if (!state || !state.active) {
        banner.style.display = 'none';
        return;
    }

    if (state.pending_reset) {
        handleCircuitBreakerPendingReset(state);
        return;
    }

    banner.style.display = 'none';
}


function handleCircuitBreakerPendingReset(state) {
    const banner = document.getElementById('cbPendingResetBanner');
    if (!banner) return;

    const trigger = (state && state.trigger) || 'unknown';
    const triggerLabel = trigger.replace(/_/g, ' ').toUpperCase();

    banner.style.display = 'flex';
    const msgEl = banner.querySelector('.cb-pending-message');
    if (msgEl) {
        msgEl.textContent = 'Circuit breaker "' + triggerLabel + '" is ready to reset. Accept or keep active?';
    }

    const acceptBtn = document.getElementById('cbAcceptReset');
    const rejectBtn = document.getElementById('cbRejectReset');

    if (acceptBtn) {
        const newAccept = acceptBtn.cloneNode(true);
        acceptBtn.parentNode.replaceChild(newAccept, acceptBtn);
        newAccept.addEventListener('click', async () => {
            newAccept.disabled = true;
            try {
                const resp = await fetch('/webhook/circuit_breaker/accept_reset', { method: 'POST', headers: { 'X-API-Key': API_KEY } });
                if (resp.ok) {
                    banner.style.display = 'none';
                    fetchCompositeBias();
                }
            } catch (e) {
                console.error('CB accept failed:', e);
            }
            newAccept.disabled = false;
        });
    }

    if (rejectBtn) {
        const newReject = rejectBtn.cloneNode(true);
        rejectBtn.parentNode.replaceChild(newReject, rejectBtn);
        newReject.addEventListener('click', async () => {
            newReject.disabled = true;
            try {
                const resp = await fetch('/webhook/circuit_breaker/reject_reset', { method: 'POST', headers: { 'X-API-Key': API_KEY } });
                if (resp.ok) {
                    banner.style.display = 'none';
                    fetchCompositeBias();
                }
            } catch (e) {
                console.error('CB reject failed:', e);
            }
            newReject.disabled = false;
        });
    }
}

// Audio alert for new signals (uses Web Audio API â€” no file needed)
function playSignalAlert(priority = false) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        gain.gain.value = 0.12;

        if (priority) {
            // Priority signal: two-tone rising chime
            osc.frequency.value = 660;
            osc.start(ctx.currentTime);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            osc.stop(ctx.currentTime + 0.4);
        } else {
            // Regular signal entering top 10: single soft tone
            osc.frequency.value = 880;
            osc.start(ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
            osc.stop(ctx.currentTime + 0.25);
        }
    } catch (e) { /* Audio not available */ }
}

function handleNewSignal(signalData) {
    if (!signalData || !signalData.signal_id) return;

    // Suppress signals for tickers with open positions
    const sigTicker = (signalData.ticker || '').toUpperCase();
    const matchingPos = openPositions.find(p => (p.ticker || '').toUpperCase() === sigTicker);
    if (matchingPos) {
        if (!isDirectionAligned(matchingPos.direction, signalData.direction)) {
            // Counter-signal — refresh positions to show warning banner
            loadOpenPositionsEnhanced();
        }
        return;
    }

    // Add to appropriate signal list
    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        signals.equity = signals.equity.filter(s => s.signal_id !== signalData.signal_id);
        // Check if this signal should jump into top 10
        const currentLowestScore = getLowestDisplayedScore();
        const newScore = signalData.score || 0;

        if (newScore > currentLowestScore || signals.equity.length < 10) {
            // Insert at correct position based on score
            insertSignalByScore(signalData, 'equity');
            refreshSignalViews();

            // Highlight new signal with animation + sound
            highlightNewSignal(signalData.signal_id);
            playSignalAlert(false);
        } else {
            // Add to queue but don't display
            signals.equity.push(signalData);
        }
    } else {
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalData.signal_id);
        signals.crypto.push(signalData);
        refreshSignalViews();
    }

}

function handlePrioritySignal(signalData) {
    // High-priority signal - insert at top with animation
    console.log('ðŸ”¥ Priority signal received:', signalData.ticker, signalData.score);

    // Suppress signals for tickers with open positions
    const sigTicker = (signalData.ticker || '').toUpperCase();
    const matchingPos = openPositions.find(p => (p.ticker || '').toUpperCase() === sigTicker);
    if (matchingPos) {
        if (!isDirectionAligned(matchingPos.direction, signalData.direction)) {
            loadOpenPositionsEnhanced();
        }
        return;
    }

    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        // Remove if already exists
        signals.equity = signals.equity.filter(s => s.signal_id !== signalData.signal_id);
        // Insert at top (newest signals always first)
        signals.equity.unshift(signalData);
    } else {
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalData.signal_id);
        signals.crypto.unshift(signalData);
    }
    
    refreshSignalViews();
    highlightNewSignal(signalData.signal_id);
    playSignalAlert(true);
}

function getLowestDisplayedScore() {
    const displayed = signals.equity.slice(0, 10);
    if (displayed.length < 10) return 0;
    return displayed.reduce((min, s) => Math.min(min, s.score || 0), 100);
}

function insertSignalByScore(signalData, type) {
    const list = type === 'equity' ? signals.equity : signals.crypto;
    
    // Remove if already exists
    const filtered = list.filter(s => s.signal_id !== signalData.signal_id);
    
    // Find insert position
    let insertIdx = filtered.findIndex(s => (s.score || 0) < (signalData.score || 0));
    if (insertIdx === -1) insertIdx = filtered.length;
    
    // Insert
    filtered.splice(insertIdx, 0, signalData);
    
    if (type === 'equity') {
        signals.equity = filtered;
    } else {
        signals.crypto = filtered;
    }
}

function highlightNewSignal(signalId) {
    setTimeout(() => {
        const card = document.querySelector(`[data-signal-id="${signalId}"]`);
        if (card) {
            card.classList.add('new-signal-highlight');
            setTimeout(() => card.classList.remove('new-signal-highlight'), 3000);
        }
    }, 100);
}

// ============================================
function updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    
    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Live';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Reconnecting...';
    }
}

// Event Listeners
function initEventListeners() {
    // Refresh button — hard browser reload (bypass cache)
    document.getElementById('refreshBtn').addEventListener('click', () => {
        location.reload(true);
    });

    // Positions refresh button
    document.getElementById('positionsRefreshBtn')?.addEventListener('click', refreshPositions);

    // Mode switcher
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const mode = e.currentTarget.dataset.mode;
            setMode(mode);
        });
    });
    
    // Price levels panel close button
    document.getElementById('priceLevelsClose')?.addEventListener('click', () => {
        document.getElementById('priceLevelsPanel').style.display = 'none';
    });

    // Chart tabs (SPY, VIX, BTC)
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            changeChartSymbol(e.target.dataset.symbol);
        });
    });

    // Savita Update Modal
    initSavitaUpdateModal();

    // Composite Bias Controls
    initCompositeBiasControls();
}

// Data Loading
async function loadInitialData() {
    // Load timeframe bias cards first; composite views are sourced from backend endpoints.
    await loadBiasData();
    await Promise.all([
        loadSignals(),
        fetchCompositeBias(),
        fetchTimeframeBias(),
        loadOpenPositionsEnhanced(),
        loadHeadlines()
    ]);

    // Schedule headline refreshes at midday and 1h before close
    startHeadlineScheduler();

    // Sync headlines height to Market Bias panel (after render settles)
    requestAnimationFrame(() => syncHeadlinesHeight());
    setTimeout(() => syncHeadlinesHeight(), 500); // second pass after late paints
    window.addEventListener('resize', syncHeadlinesHeight);

    // Initialize timeframe card toggles
    initTimeframeToggles();

    // bias-auto/shift-status polling removed (Phase 0D) — endpoint was dead
    
    // Refresh timeframe data every 2 minutes
    setInterval(fetchTimeframeBias, 2 * 60 * 1000);

    // Pivot health checks
    checkPivotHealth();
    setInterval(checkPivotHealth, 5 * 60 * 1000);

    // Redis health checks
    checkRedisHealth();
    setInterval(checkRedisHealth, 2 * 60 * 1000);

    // Position refresh every 30 seconds (visibility-gated). WebSocket pushes real-time updates.
    setInterval(() => {
        if (document.visibilityState === 'visible') {
            loadOpenPositionsEnhanced();
        }
    }, 30 * 1000);
}

let cryptoTvWidget = null;
let cryptoCurrentSymbol = 'BTCUSD';

function initCryptoScalper() {
    // Top coin chips
    const topCoins = document.getElementById('cryptoTopCoins');
    if (topCoins) {
        topCoins.querySelectorAll('.coin-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                topCoins.querySelectorAll('.coin-chip').forEach(c => c.classList.remove('active'));
                chip.addEventListener('click', () => {});
                chip.classList.add('active');
                const sym = chip.dataset.symbol;
                if (sym && sym !== cryptoCurrentSymbol) {
                    cryptoCurrentSymbol = sym;
                    initCryptoChart();
                }
            });
        });
    }

    const sortSelect = document.getElementById('cryptoSignalSort');
    if (sortSelect) {
        sortSelect.addEventListener('change', renderCryptoSignals);
    }

    // Chart tab switching (legacy tabs) + chips already handle above
    const chartTabs = document.getElementById('cryptoChartTabs');
    if (chartTabs) {
        chartTabs.querySelectorAll('.chart-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                chartTabs.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const sym = tab.dataset.symbol;
                if (sym && sym !== cryptoCurrentSymbol) {
                    cryptoCurrentSymbol = sym;
                    initCryptoChart();
                }
            });
        });
    }

    // Strategy filter checkboxes
    document.querySelectorAll('.crypto-strategy-cb').forEach(cb => {
        cb.addEventListener('change', renderCryptoSignals);
    });
    const dirLong = document.getElementById('cryptoFilterLong');
    const dirShort = document.getElementById('cryptoFilterShort');
    if (dirLong) dirLong.addEventListener('change', renderCryptoSignals);
    if (dirShort) dirShort.addEventListener('change', renderCryptoSignals);
    const autoBiasToggle = document.getElementById('cryptoAutoBiasToggle');
    if (autoBiasToggle) {
        autoBiasToggle.addEventListener('change', () => {
            applyCryptoBiasPreset();
            renderCryptoSignals();
        });
    }
    const scoreThreshold = document.getElementById('cryptoScoreThreshold');
    if (scoreThreshold) scoreThreshold.addEventListener('input', renderCryptoSignals);

    // Signal action delegation
    const signalList = document.getElementById('cryptoSignalsList');
    if (signalList) {
        signalList.addEventListener('click', handleCryptoSignalAction);
    }

    loadCryptoKeyLevels();
    setInterval(loadCryptoKeyLevels, 10 * 60 * 1000);

    refreshCryptoWma9();
    if (cryptoWmaTimer) clearInterval(cryptoWmaTimer);
    cryptoWmaTimer = setInterval(refreshCryptoWma9, 15 * 60 * 1000);

    // Start 5s market polling only if the crypto view is currently visible.
    if (document.body.dataset.mode === APP_MODES.CRYPTO) {
        startCryptoMarketPolling();
    }
}

function startCryptoMarketPolling() {
    loadCryptoMarketData();
    if (cryptoMarketTimer) clearInterval(cryptoMarketTimer);
    cryptoMarketTimer = setInterval(loadCryptoMarketData, CRYPTO_MARKET_POLL_MS);
}

function stopCryptoMarketPolling() {
    if (!cryptoMarketTimer) return;
    clearInterval(cryptoMarketTimer);
    cryptoMarketTimer = null;
}

function initCryptoChart() {
    const container = document.getElementById('crypto-tradingview-widget');
    if (!container) return;
    if (typeof TradingView === 'undefined') return;

    // TradingView requires a visible container with non-zero dimensions.
    // If the container is not yet laid out (e.g. parent is hidden or has zero size),
    // defer the init by one animation frame so the browser can reflow first.
    const parentContainer = document.getElementById('cryptoChartContainer');
    if (parentContainer && parentContainer.offsetWidth === 0) {
        requestAnimationFrame(() => setTimeout(initCryptoChart, 50));
        return;
    }

    container.innerHTML = '';
    cryptoTvWidget = new TradingView.widget({
        symbol: cryptoCurrentSymbol,
        interval: '15',
        timezone: 'America/New_York',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0a0e27',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        container_id: 'crypto-tradingview-widget',
        width: '100%',
        height: '100%',
        studies: [
            { id: 'MASimple@tv-basicstudies', inputs: { length: 50 } },
            { id: 'MASimple@tv-basicstudies', inputs: { length: 200 } }
        ],
        overrides: {
            'mainSeriesProperties.candleStyle.upColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.downColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.borderUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.borderDownColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.wickUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.wickDownColor': '#FF6B35',
            'paneProperties.background': '#0a0e27',
            'paneProperties.backgroundType': 'solid',
            'paneProperties.vertGridProperties.color': '#1e293b',
            'paneProperties.horzGridProperties.color': '#1e293b',
            'scalesProperties.textColor': '#94a3b8',
            'scalesProperties.backgroundColor': '#0a0e27',
            'paneProperties.crossHairProperties.color': '#F7931A'
        }
    });
}

function handleCryptoSignalAction(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const card = btn.closest('.crypto-signal-card');
    if (!card) return;
    const signalId = card.dataset.signalId;
    if (!signalId) return;

    const action = btn.dataset.action;
    if (action === 'select') {
        // Find signal data
        const signal = signals.crypto.find(s => s.signal_id === signalId);
        if (signal) {
            openCryptoAcceptModal(signal);
        }
    } else if (action === 'dismiss') {
        dismissCryptoSignal(signalId);
    } else if (action === 'view-chart') {
        // Normalize the ticker: strip any trailing USDT or USD suffix before building symbol
        const rawTicker = btn.textContent.trim().toUpperCase().replace(/USDT?$/, '');
        if (rawTicker) {
            cryptoCurrentSymbol = rawTicker + 'USD';
            initCryptoChart();
            // Highlight matching tab (if no tab matches, all tabs become inactive â€” graceful)
            const tabs = document.getElementById('cryptoChartTabs');
            if (tabs) {
                tabs.querySelectorAll('.chart-tab').forEach(t => {
                    t.classList.toggle('active', t.dataset.symbol === cryptoCurrentSymbol);
                });
            }
        }
    }
}

function openCryptoAcceptModal(signal) {
    // Reuse the existing position entry modal from hub mode.
    // IMPORTANT: must set pendingPositionSignal so confirmPositionEntry() has the data.
    const modal = document.getElementById('positionEntryModal');
    if (!modal) return;

    // Wire up pendingPositionSignal so the shared confirmPositionEntry handler works
    pendingPositionSignal = signal;
    pendingPositionCard = null; // No card element ref in crypto mode; skip animation

    const tickerDisplay = document.getElementById('positionTickerDisplay');
    const dirDisplay = document.getElementById('positionDirectionDisplay');
    const entryInput = document.getElementById('positionEntryPrice');
    const qtyInput = document.getElementById('positionQuantity');
    const qtyLabel = document.getElementById('positionQtyLabel');
    const summaryStop = document.getElementById('summaryStop');
    const summaryTarget = document.getElementById('summaryTarget');
    const summarySize = document.getElementById('summarySize');
    const summaryRisk = document.getElementById('summaryRisk');

    if (tickerDisplay) tickerDisplay.textContent = signal.ticker || '--';
    if (dirDisplay) {
        dirDisplay.textContent = signal.direction || 'LONG';
        dirDisplay.className = 'position-direction-display ' + (signal.direction || 'LONG');
    }
    if (entryInput) entryInput.value = signal.entry_price ? parseFloat(signal.entry_price).toFixed(2) : '';

    // Pre-fill sizing from enrichment if available (Breakout risk model)
    const enrichment = typeof signal.enrichment_data === 'string'
        ? JSON.parse(signal.enrichment_data || '{}') : (signal.enrichment_data || {});
    const sizing = enrichment.position_sizing || {};

    if (qtyInput) {
        qtyInput.value = sizing.contracts ? sizing.contracts : '';
        qtyInput.placeholder = 'BTC Contracts';
    }
    if (qtyLabel) qtyLabel.textContent = sizing.leverage
        ? `Quantity (BTC) — ${sizing.leverage}x leverage`
        : 'Quantity (Contracts) *';
    if (summaryStop) summaryStop.textContent = signal.stop_loss ? `$${parseFloat(signal.stop_loss).toLocaleString()}` : '--';
    if (summaryTarget) summaryTarget.textContent = signal.target_1 ? `$${parseFloat(signal.target_1).toLocaleString()}` : '--';
    if (summarySize) summarySize.textContent = sizing.notional_usd ? `$${sizing.notional_usd.toLocaleString()}` : '$--';
    if (summaryRisk) summaryRisk.textContent = sizing.risk_usd ? `$${sizing.risk_usd} (${sizing.risk_pct}%)` : '$--';

    // Use classList.add('active') to match the hub modal open/close pattern
    modal.classList.add('active');
}

async function dismissCryptoSignal(signalId) {
    try {
        await fetch(`${API_URL}/trade-ideas/${signalId}/status`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({ status: 'DISMISSED', decision_source: 'dashboard' })
        });
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalId);
        renderCryptoSignals();
    } catch (err) {
        console.error('Error dismissing crypto signal:', err);
    }
}

async function loadSignals() {
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        console.log('ðŸ“¡ Loaded signals:', data);
        
        if (data.status === 'success' && data.signals) {
            // Merge counter-trend signals that aren't already in the main list
            const allSignals = [...data.signals];
            if (data.counter_trend_signals && data.counter_trend_signals.length > 0) {
                const mainIds = new Set(allSignals.map(s => s.signal_id));
                for (const ct of data.counter_trend_signals) {
                    ct.is_counter_trend = true;
                    if (!mainIds.has(ct.signal_id)) {
                        allSignals.push(ct);
                    }
                }
            }
            
            // Separate equity and crypto signals (be more flexible with asset_class matching)
            const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
            
            signals.equity = allSignals.filter(s => {
                // If explicitly marked as EQUITY
                if (s.asset_class === 'EQUITY') return true;
                // If no asset_class but ticker doesn't look like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return !cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            signals.crypto = allSignals.filter(s => {
                // If explicitly marked as CRYPTO
                if (s.asset_class === 'CRYPTO') return true;
                // If no asset_class but ticker looks like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            console.log(`ðŸ“Š Signals loaded: ${signals.equity.length} equity, ${signals.crypto.length} crypto`);
            console.log('ðŸª™ Crypto signals:', signals.crypto);
            
            resetTradeIdeasPagination();
            
            // Force render signals with a small delay to ensure DOM is ready
            setTimeout(() => {
                refreshSignalViews();
            }, 100);
        } else {
            console.warn('No signals in response or error:', data);
        }
    } catch (error) {
        console.error('Error loading signals:', error);
    }
}

function resetTradeIdeasPagination() {
    tradeIdeasPagination = {
        equity: { offset: signals.equity.length, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false },
        crypto: { offset: signals.crypto.length, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false }
    };
}

function syncTradeIdeasOffset(assetType) {
    if (!tradeIdeasPagination[assetType]) return;
    tradeIdeasPagination[assetType].offset = signals[assetType].length;
}

async function loadBiasData() {
    // bias-auto/status endpoint removed (Phase 0D). Use composite endpoints directly.
    await loadBiasDataFallback();
    checkAndApplyBiasAlignment();
    renderCryptoBiasSummary();
}

function normalizeCompositeBiasLevel(level) {
    if (!level) return 'NEUTRAL';
    const raw = String(level).toUpperCase().replace(/\s+/g, '_');
    const map = {
        MAJOR_TORO: 'TORO_MAJOR',
        MINOR_TORO: 'TORO_MINOR',
        LEAN_TORO: 'TORO_MINOR',
        LEAN_URSA: 'URSA_MINOR',
        MINOR_URSA: 'URSA_MINOR',
        MAJOR_URSA: 'URSA_MAJOR',
        TORO_MAJOR: 'TORO_MAJOR',
        TORO_MINOR: 'TORO_MINOR',
        URSA_MINOR: 'URSA_MINOR',
        URSA_MAJOR: 'URSA_MAJOR',
        NEUTRAL: 'NEUTRAL'
    };
    return map[raw] || 'NEUTRAL';
}

function normalizeDailyBiasLevel(level) {
    if (!level) return 'NEUTRAL';
    return String(level).toUpperCase().replace(/\s+/g, '_');
}

function timeframeVoteToBiasLabel(vote) {
    if (vote >= 6) return 'MAJOR_TORO';
    if (vote >= 3) return 'MINOR_TORO';
    if (vote <= -6) return 'MAJOR_URSA';
    if (vote <= -3) return 'MINOR_URSA';
    return 'NEUTRAL';
}

function scoreToTimeframeVote(score) {
    if (!Number.isFinite(score)) return 0;
    return Math.round(score * 10);
}

function biasTrendToMomentum(trend) {
    const value = String(trend || '').toUpperCase();
    if (value === 'IMPROVING') return 'strengthening';
    if (value === 'DECLINING') return 'weakening';
    return 'stable';
}

function compositeLevelToScore(level) {
    const normalized = normalizeCompositeBiasLevel(level);
    const scoreMap = {
        TORO_MAJOR: 0.9,
        TORO_MINOR: 0.45,
        NEUTRAL: 0,
        URSA_MINOR: -0.45,
        URSA_MAJOR: -0.9
    };
    return scoreMap[normalized] ?? 0;
}

function scoreToCompositeLevel(score) {
    if (score >= 0.6) return 'TORO_MAJOR';
    if (score >= 0.2) return 'TORO_MINOR';
    if (score <= -0.6) return 'URSA_MAJOR';
    if (score <= -0.2) return 'URSA_MINOR';
    return 'NEUTRAL';
}

function factorMapToRows(factorMap) {
    if (!factorMap || typeof factorMap !== 'object') return [];
    return Object.entries(factorMap).map(([factorId, factorData]) => {
        const voteRaw = Number(factorData?.vote ?? 0);
        const vote = Number.isFinite(voteRaw) ? voteRaw : 0;
        const score = Math.max(-1, Math.min(1, vote / 2));
        const signal = factorData?.details?.signal || factorData?.signal || 'NEUTRAL';
        const detail = factorData?.details ? JSON.stringify(factorData.details) : '';
        return {
            factor_id: factorId,
            weight: 1,
            description: '',
            stale: false,
            score,
            signal,
            detail
        };
    });
}

async function fetchDailyBiasPrimary() {
    try {
        const resp = await fetch(`${API_URL}/bias/DAILY`);
        if (!resp.ok) {
            throw new Error(`/bias/DAILY returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data || typeof data !== 'object') {
            throw new Error('/bias/DAILY returned invalid payload');
        }
        _dailyBiasPrimaryData = data;
        return data;
    } catch (err) {
        console.error('Failed to fetch daily bias primary:', err);
        return null;
    }
}

async function fetchCompositeBias() {
    try {
        const [compositeResp, dailyData] = await Promise.all([
            fetch(`${API_URL}/bias/composite`),
            fetchDailyBiasPrimary(),
        ]);
        if (!compositeResp.ok) {
            throw new Error(`/bias/composite returned HTTP ${compositeResp.status}`);
        }
        const data = await compositeResp.json();
        if (!data || typeof data !== 'object') {
            throw new Error('/bias/composite returned invalid payload');
        }
        renderCompositeBias(data, dailyData);
    } catch (err) {
        console.error('Failed to fetch composite bias:', err);
        showCompositeError();
    }
}

function showCompositeError() {
    const levelEl = document.getElementById('compositeBiasLevel');
    const scoreEl = document.getElementById('compositeBiasScore');
    const confEl = document.getElementById('compositeConfidence');
    const secondaryEl = document.getElementById('compositeBiasSecondary');
    const lastUpdateEl = document.getElementById('compositeLastUpdate');

    if (levelEl) levelEl.textContent = 'UNKNOWN';
    if (scoreEl) scoreEl.textContent = '(--)';
    if (confEl) confEl.textContent = 'LOW';
    if (secondaryEl) secondaryEl.textContent = 'Composite: --';
    if (lastUpdateEl) lastUpdateEl.textContent = 'Last update: --';
}

function renderCompositeBias(data, dailyData = null) {
    if (!data) return;

    // Cache for use by crypto bias bar (avoids reading from hub DOM elements)
    _compositeBiasData = data;
    if (dailyData && typeof dailyData === 'object') {
        _dailyBiasPrimaryData = dailyData;
    }

    const banner = document.getElementById('compositeBiasBanner');
    const levelEl = document.getElementById('compositeBiasLevel');
    const scoreEl = document.getElementById('compositeBiasScore');
    const confEl = document.getElementById('compositeConfidence');
    const secondaryEl = document.getElementById('compositeBiasSecondary');
    const overrideEl = document.getElementById('compositeOverrideIndicator');
    const factorList = document.getElementById('compositeFactorList');
    const activeCountEl = document.getElementById('factorActiveCount');
    const lastUpdateEl = document.getElementById('compositeLastUpdate');

    const dailySource = _dailyBiasPrimaryData || dailyBiasFullData || {};
    // Use composite bias_level as primary (includes CB floor/cap overrides),
    // fall back to old daily bias system only if composite unavailable
    const dailyLevel = normalizeDailyBiasLevel(data.bias_level || dailySource.level || 'NEUTRAL');
    const dailyVoteRaw = Number(dailySource?.details?.total_vote);
    const dailyVote = Number.isFinite(dailyVoteRaw) ? Math.trunc(dailyVoteRaw) : null;
    const dailyColorKey = normalizeCompositeBiasLevel(dailyLevel);
    const colors = BIAS_COLORS[dailyColorKey] || BIAS_COLORS.NEUTRAL;

    // Update daily quote to match current bias
    updateDailyQuote(dailyColorKey);

    const scoreValue = typeof data.composite_score === 'number'
        ? data.composite_score
        : parseFloat(data.composite_score || 0);
    const confidence = (data.confidence || 'LOW').toUpperCase();
    const activeCount = Array.isArray(data.active_factors) ? data.active_factors.length : null;
    const staleCount = Array.isArray(data.stale_factors) ? data.stale_factors.length : null;
    const totalCount = Number.isFinite(activeCount) && Number.isFinite(staleCount)
        ? activeCount + staleCount
        : (data.factors && typeof data.factors === 'object' ? Object.keys(data.factors).length : null);

    if (banner) {
        banner.style.background = colors.bg;
        banner.style.borderColor = colors.accent;
    }
    if (levelEl) {
        levelEl.textContent = dailyLevel.replace(/_/g, ' ');
        levelEl.style.color = colors.accent;
    }
    if (scoreEl) {
        // Show composite score when available, fall back to old daily vote
        const scoreText = Number.isFinite(scoreValue)
            ? scoreValue.toFixed(2)
            : (dailyVote === null ? '--' : `${dailyVote >= 0 ? '+' : ''}${dailyVote}`);
        scoreEl.textContent = `(${scoreText})`;
    }
    if (confEl) {
        const suffix = Number.isFinite(activeCount) && Number.isFinite(totalCount)
            ? ` (${activeCount}/${totalCount} active)`
            : '';
        confEl.textContent = `${confidence}${suffix}`;
        confEl.style.color = '#ffffff';
    }
    if (secondaryEl) {
        const compositeLevel = String(data.bias_level || 'NEUTRAL').replace(/_/g, ' ');
        const compositeScoreText = Number.isFinite(scoreValue) ? scoreValue.toFixed(2) : '--';
        const staleLabel = Number.isFinite(staleCount)
            ? ` - ${staleCount} stale factor${staleCount === 1 ? '' : 's'}`
            : '';
        secondaryEl.textContent = `Composite: ${compositeLevel} (${compositeScoreText})${staleLabel}`;
    }

    if (overrideEl) {
        const cb = data.circuit_breaker;
        if (data.override) {
            overrideEl.style.display = 'block';
            overrideEl.textContent = 'Override active: ' + data.override.replace(/_/g, ' ');
            overrideEl.className = 'override-indicator';
        } else if (cb && cb.active && cb.pending_reset) {
            overrideEl.style.display = 'block';
            overrideEl.textContent = 'CB pending reset: ' + (cb.trigger || '').replace(/_/g, ' ') + ' (fading)';
            overrideEl.className = 'override-indicator cb-pending';
        } else if (cb && cb.active) {
            overrideEl.style.display = 'block';
            overrideEl.textContent = 'Circuit breaker: ' + (cb.trigger || '').replace(/_/g, ' ');
            overrideEl.className = 'override-indicator cb-active';
        } else {
            overrideEl.style.display = 'none';
        }
    }

    // Show/hide pending reset banner from API response
    if (data.circuit_breaker && data.circuit_breaker.pending_reset) {
        handleCircuitBreakerPendingReset(data.circuit_breaker);
    }

    if (factorList) {
        const activeSet = new Set(data.active_factors || []);
        const staleSet = new Set(data.stale_factors || []);
        const factorsMap = data.factors && typeof data.factors === 'object' ? data.factors : {};
        const discoveredFactorIds = new Set([
            ...Object.keys(factorsMap),
            ...Array.from(activeSet),
            ...Array.from(staleSet)
        ]);

        const factorOrderMap = new Map(COMPOSITE_FACTOR_DISPLAY_ORDER.map((id, idx) => [id, idx]));
        const sortedFactorIds = Array.from(discoveredFactorIds).sort((a, b) => {
            const ai = factorOrderMap.has(a) ? factorOrderMap.get(a) : Number.MAX_SAFE_INTEGER;
            const bi = factorOrderMap.has(b) ? factorOrderMap.get(b) : Number.MAX_SAFE_INTEGER;
            if (ai !== bi) return ai - bi;
            return a.localeCompare(b);
        });

        factorList.innerHTML = '';

        sortedFactorIds.forEach((factorId) => {
            const factor = factorsMap[factorId] || null;
            const isActive = activeSet.has(factorId);
            const isStale = staleSet.has(factorId) || !isActive;
            const score = factor && typeof factor.score === 'number' ? factor.score : null;
            const barPct = score !== null ? Math.min(100, Math.abs(score) * 100) : 0;

            const barColor = score === null ? '#455a64'
                : score <= -0.6 ? '#e5370e'
                : score <= -0.2 ? '#ff9800'
                : score >= 0.6 ? '#00e676'
                : score >= 0.2 ? '#66bb6a' : '#78909c';

            const row = document.createElement('div');
            row.className = `factor-row${isStale ? ' stale' : ''}`;
            row.innerHTML = `
                <span class="factor-status">${isActive ? 'o' : '-'}</span>
                <span class="factor-name">${formatFactorName(factorId)}</span>
                <div class="factor-bar">
                    <div class="factor-bar-fill" style="width:${barPct}%;background:${barColor}"></div>
                </div>
                <span class="factor-score">${score !== null && isActive ? score.toFixed(2) : 'STALE'}</span>
                <span class="factor-signal" style="color:${barColor}">${score !== null && isActive ? (factor.signal || '').replace(/_/g, ' ') : '?'}</span>
            `;

            if (factor && factor.detail) {
                row.title = factor.detail;
                row.style.cursor = 'pointer';
                row.addEventListener('click', () => {
                    const existing = row.querySelector('.factor-detail');
                    if (existing) {
                        existing.remove();
                    } else {
                        const detail = document.createElement('div');
                        detail.className = 'factor-detail';
                        detail.textContent = factor.detail;
                        row.appendChild(detail);
                    }
                });
            }

            factorList.appendChild(row);
        });

        if (activeCountEl) {
            const total = sortedFactorIds.length;
            const active = (data.active_factors || []).length;
            activeCountEl.textContent = `${active}/${total} active`;
        }
    }

    if (lastUpdateEl && data.timestamp) {
        const timeAgo = getTimeAgo(new Date(data.timestamp));
        lastUpdateEl.textContent = `Last update: ${timeAgo}`;
    }
}

function initCompositeBiasControls() {
    const toggle = document.getElementById('factorBreakdownToggle');
    const list = document.getElementById('compositeFactorList');
    const caret = toggle ? toggle.querySelector('.factor-breakdown-caret') : null;

    if (toggle && list) {
        toggle.addEventListener('click', () => {
            const isOpen = list.style.display !== 'none';
            list.style.display = isOpen ? 'none' : 'flex';
            if (caret) caret.textContent = isOpen ? '>' : 'v';
        });
    }

    const applyBtn = document.getElementById('compositeOverrideApply');
    const clearBtn = document.getElementById('compositeOverrideClear');
    const selectEl = document.getElementById('compositeOverrideSelect');

    if (applyBtn && selectEl) {
        applyBtn.addEventListener('click', async () => {
            const level = selectEl.value;
            if (!level) return;
            const reason = prompt('Reason for override?');
            if (!reason) return;

            await fetch(`${API_URL}/bias/override`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({
                    level,
                    reason,
                    expires_hours: 24,
                })
            });

            fetchCompositeBias();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            await fetch(`${API_URL}/bias/override`, { method: 'DELETE', headers: { 'X-API-Key': API_KEY } });
            fetchCompositeBias();
        });
    }
}

// =========================================================================
// TIMEFRAME FACTOR CARDS (Intraday / Swing / Macro)
// =========================================================================

async function fetchTimeframeBias() {
    try {
        const resp = await fetch(`${API_URL}/bias/composite/timeframes`);
        if (!resp.ok) {
            throw new Error(`/bias/composite/timeframes returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data || !data.timeframes || typeof data.timeframes !== 'object') {
            throw new Error('/bias/composite/timeframes returned invalid payload');
        }

        if (data && data.timeframes) {
            // Backfill cache only from backend-computed timeframe payload.
            if (data.composite_bias && typeof data.composite_score === 'number') {
                _compositeBiasData = {
                    ...(typeof _compositeBiasData === 'object' && _compositeBiasData ? _compositeBiasData : {}),
                    bias_level: data.composite_bias,
                    composite_score: data.composite_score,
                    confidence: data.confidence || _compositeBiasData?.confidence || 'LOW'
                };
            }

            renderTimeframeCards(data);
            renderSectorRotationStrip(data.sector_rotation);
            renderCryptoBiasSummary();
            
            // Apply pulse to composite banner at extremes
            const banner = document.getElementById('compositeBiasBanner');
            if (banner) {
                banner.classList.remove('pulse-toro', 'pulse-ursa');
                if (data.composite_bias === 'TORO_MAJOR') banner.classList.add('pulse-toro');
                else if (data.composite_bias === 'URSA_MAJOR') banner.classList.add('pulse-ursa');
            }

            // Set bias-colored borders on all major sections
            const biasColors = BIAS_COLORS[data.composite_bias] || BIAS_COLORS.NEUTRAL;
            document.documentElement.style.setProperty('--bias-border-color', biasColors.accent);
        }
    } catch (err) {
        console.error('Failed to fetch timeframe bias:', err);
    }
}

function renderTimeframeCards(data) {
    const tfNames = ['intraday', 'swing', 'macro'];
    const cardIds = { intraday: 'tfIntraday', swing: 'tfSwing', macro: 'tfMacro' };

    for (const tf of tfNames) {
        const tfData = data.timeframes[tf];
        if (!tfData) continue;

        const card = document.getElementById(cardIds[tf]);
        if (!card) continue;

        // Use API-computed bias_level (same score_to_bias thresholds as composite)
        const apiLevel = tfData.bias_level || '';
        const visualLevel = normalizeCompositeBiasLevel(apiLevel) || 'NEUTRAL';
        // Fallback to vote conversion only if API didn't provide bias_level
        const displayLevel = apiLevel ? visualLevel : (() => {
            const voteValue = scoreToTimeframeVote(typeof tfData.sub_score === 'number' ? tfData.sub_score : 0);
            return normalizeCompositeBiasLevel(timeframeVoteToBiasLabel(voteValue));
        })();
        const subScore = typeof tfData.sub_score === 'number' ? tfData.sub_score : 0;
        const momentum = tfData.momentum || 'stable';

        // Update level
        const levelEl = card.querySelector('.tf-level');
        if (levelEl) {
            levelEl.textContent = visualLevel.replace(/_/g, ' ');
        }

        // Update score — show sub_score as compact value
        const scoreEl = card.querySelector('.tf-score');
        if (scoreEl) {
            const scoreText = `${subScore >= 0 ? '+' : ''}${subScore.toFixed(2)}`;
            scoreEl.textContent = `(${scoreText})`;
        }

        // Update momentum
        const momEl = card.querySelector('.tf-momentum');
        if (momEl) {
            const arrows = { strengthening: '^', weakening: 'v', stable: '->' };
            const labels = { strengthening: 'Strengthening', weakening: 'Weakening', stable: 'Stable' };
            momEl.className = `tf-momentum ${momentum}`;
            momEl.innerHTML = `<span class="tf-momentum-arrow">${arrows[momentum] || '->'}</span> ${labels[momentum] || 'Stable'}`;
        }

        // Update divergence
        const divEl = card.querySelector('.tf-divergence');
        if (divEl) {
            if (tfData.divergent) {
                const compDir = data.composite_score > 0 ? 'bullish' : 'bearish';
                divEl.textContent = `Diverging from composite (${compDir})`;
                divEl.style.display = 'block';
            } else {
                divEl.style.display = 'none';
            }
        }

        // Apply bias color class
        card.className = `tf-card ${visualLevel}`;

        // Pulse at extremes
        card.classList.remove('pulse-toro', 'pulse-ursa');
        if (visualLevel === 'TORO_MAJOR') card.classList.add('pulse-toro');
        else if (visualLevel === 'URSA_MAJOR') card.classList.add('pulse-ursa');

        // Render factor bars
        const factorsEl = card.querySelector('.tf-factors');
        if (factorsEl && tfData.factors) {
            factorsEl.innerHTML = tfData.factors.map(f => {
                const fScore = f.score !== null ? f.score : 0;
                const pct = Math.abs(fScore) * 50; // 0-50% of bar width
                const dir = fScore >= 0 ? 'bullish' : 'bearish';
                const staleClass = f.stale ? 'stale' : '';
                const name = f.factor_id.replace(/_/g, ' ');
                return `
                    <div class="tf-factor-row ${staleClass}">
                        <span class="tf-factor-name">${name}</span>
                        <div class="tf-factor-bar">
                            <div class="tf-factor-bar-fill ${dir}" style="width:${pct}%"></div>
                        </div>
                        <span class="tf-factor-score">${
                            f.score !== null
                                ? (fScore >= 0 ? '+' : '') + fScore.toFixed(2)
                                : (f.stale ? 'STALE' : '--')
                        }</span>
                    </div>`;
            }).join('');
        }
    }
}

// =========================================================================
// SECTOR ROTATION STRIP
// =========================================================================

function renderSectorRotationStrip(sectorData) {
    const container = document.getElementById('sectorChips');
    if (!container) return;

    if (!sectorData || !sectorData.sectors || sectorData.sectors.length === 0) {
        container.innerHTML = '<span style="font-size:10px;color:var(--text-secondary)">Sector rotation data loading...</span>';
        return;
    }

    // Sort: SURGING first, then STEADY, then DUMPING (by rotation momentum)
    const sectors = [...sectorData.sectors].sort((a, b) => (b.rotation_momentum || 0) - (a.rotation_momentum || 0));

    container.innerHTML = sectors.map(s => {
        const status = s.status || 'STEADY';
        const arrow = status === 'SURGING' ? '^' : (status === 'DUMPING' ? 'v' : '-');
        const mom = s.rotation_momentum !== undefined ? (s.rotation_momentum >= 0 ? '+' : '') + s.rotation_momentum.toFixed(1) + '%' : '';
        const rs5 = s.rs_5d !== undefined ? (s.rs_5d >= 0 ? '+' : '') + s.rs_5d.toFixed(1) + '%' : '--';
        const rs20 = s.rs_20d !== undefined ? (s.rs_20d >= 0 ? '+' : '') + s.rs_20d.toFixed(1) + '%' : '--';
        const rankChange = s.rank_change_5d !== undefined ? (s.rank_change_5d > 0 ? '+' + s.rank_change_5d : s.rank_change_5d) : '--';
        const accel = s.acceleration || 'unknown';

        return `
            <div class="sector-chip ${status}" title="${s.sector}">
                <span class="sector-chip-arrow">${arrow}</span>
                ${s.etf}
                <div class="sector-tooltip">
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">${s.sector}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">5d RS</span><span>${rs5}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">20d RS</span><span>${rs20}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Momentum</span><span>${mom}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Rank Delta</span><span>${rankChange}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Accel</span><span>${accel}</span></div>
                </div>
            </div>`;
    }).join('');

    // Make sector chips clickable to change chart
    container.querySelectorAll('.sector-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            if (e.target.closest('.sector-tooltip')) return;
            const match = chip.textContent.trim().match(/[A-Z]{2,5}/);
            if (match && match[0]) changeChartSymbol(match[0]);
        });
    });
}

// Initialize timeframe card expand/collapse toggles
function initTimeframeToggles() {
    document.querySelectorAll('.tf-expand-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const targetId = toggle.dataset.target;
            const target = document.getElementById(targetId);
            if (target) {
                const isOpen = target.style.display !== 'none';
                target.style.display = isOpen ? 'none' : 'flex';
                toggle.textContent = isOpen ? 'Factors >' : 'Factors v';
            }
        });
    });
}


function checkPivotHealth() {
    const indicators = Array.from(document.querySelectorAll('[data-pivot-health="true"]'));
    if (!indicators.length) return;

    const updateIndicators = (status) => {
        indicators.forEach(indicator => {
            indicator.classList.remove('online', 'offline');
            if (status) indicator.classList.add(status);
        });
    };

    fetch(`${API_URL}/bias/health`)
        .then(resp => resp.ok ? resp.json() : null)
        .then(data => {
            if (!data || !data.last_heartbeat) {
                updateIndicators(null);
                return;
            }

            const lastHeartbeat = new Date(data.last_heartbeat);
            const minutesAgo = (Date.now() - lastHeartbeat.getTime()) / 60000;
            if (minutesAgo < 30) {
                updateIndicators('online');
            } else {
                updateIndicators('offline');
            }
        })
        .catch(() => {
            updateIndicators(null);
        });
}

function checkRedisHealth() {
    const indicators = Array.from(document.querySelectorAll('[data-redis-health="true"]'));
    if (!indicators.length) return;

    const updateIndicators = (status, title) => {
        indicators.forEach(indicator => {
            indicator.classList.remove('ok', 'throttled', 'error');
            if (status) indicator.classList.add(status);
            if (title) {
                indicator.title = title;
            } else {
                indicator.removeAttribute('title');
            }
        });
    };

    fetch(`${API_URL}/redis/health`)
        .then(resp => resp.ok ? resp.json() : null)
        .then(data => {
            if (!data) {
                updateIndicators(null);
                return;
            }

            const status = data.status || 'unknown';
            const lastError = data.last_error || null;
            const lastErrorAt = data.last_error_at ? new Date(data.last_error_at) : null;
            const minutesAgo = lastErrorAt ? Math.round((Date.now() - lastErrorAt.getTime()) / 60000) : null;

            if (status === 'throttled') {
                const suffix = Number.isFinite(minutesAgo) ? ` (${minutesAgo}m ago)` : '';
                updateIndicators('throttled', `Throttled${suffix}: ${lastError || ''}`);
                return;
            }

            if (status === 'error') {
                const suffix = Number.isFinite(minutesAgo) ? ` (${minutesAgo}m ago)` : '';
                updateIndicators('error', `Error${suffix}: ${lastError || ''}`);
                return;
            }

            if (status === 'ok') {
                updateIndicators('ok');
                return;
            }

            updateIndicators(null);
        })
        .catch(() => {
            updateIndicators(null);
        });
}

function formatFactorName(factorId) {
    return factorId
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

function getTimeAgo(date) {
    if (!date || Number.isNaN(date.getTime())) return '--';
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
}

function flashCompositeBanner() {
    const banner = document.getElementById('compositeBiasBanner');
    if (!banner) return;
    banner.classList.add('flash');
    setTimeout(() => banner.classList.remove('flash'), 1500);
}

// ==================== PORTFOLIO BALANCES (Brief 07-E) ====================

async function loadPortfolioBalances() {
    try {
        const res = await fetch(`${API_URL.replace('/api', '')}/api/portfolio/balances`);
        if (!res.ok) return;
        const accounts = await res.json();

        const container = document.getElementById('balance-rows');
        const totalEl = document.getElementById('balance-total');
        const updatedEl = document.getElementById('balance-updated-time');

        if (!container || !accounts.length) return;

        let total = 0;
        let latestUpdate = null;
        let html = '';

        for (const acct of accounts) {
            const bal = parseFloat(acct.balance);
            total += bal;

            if (acct.updated_at && (!latestUpdate || new Date(acct.updated_at) > new Date(latestUpdate))) {
                latestUpdate = acct.updated_at;
            }

            const isRH = acct.broker === 'robinhood';
            const rowClass = isRH ? 'active-account' : 'passive-account';

            html += `<div class="balance-row ${rowClass}">
                <span class="balance-label">${escapeHtml(acct.account_name)}</span>
                <span class="balance-value">$${bal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
            </div>`;

            if (isRH && acct.cash != null) {
                html += `<div class="balance-row active-account">
                    <span class="balance-sub">Cash: $${parseFloat(acct.cash).toLocaleString('en-US', {minimumFractionDigits: 2})} · BP: $${parseFloat(acct.buying_power).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                </div>`;
            }
        }

        container.innerHTML = html;
        totalEl.textContent = `$${total.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        if (latestUpdate) {
            const ago = getTimeAgo(new Date(latestUpdate));
            updatedEl.textContent = `Updated ${ago}`;
        }
    } catch (err) {
        console.error('Failed to load portfolio balances:', err);
    }
}

// ==================== OPEN POSITIONS (Brief 07-E) ====================

async function loadPortfolioPositions() {
    try {
        const res = await fetch(`${API_URL.replace('/api', '')}/api/portfolio/positions`);
        if (!res.ok) return;
        const positions = await res.json();

        const tbody = document.getElementById('portfolio-positions-tbody');
        const countEl = document.getElementById('positions-count');
        if (!tbody) return;

        countEl.textContent = positions.length;

        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary);">No open positions</td></tr>';
            return;
        }

        let html = '';
        for (const pos of positions) {
            let desc = '';
            if (pos.position_type === 'option_spread') {
                desc = `${pos.option_type || ''} ${pos.strike}/${pos.short_strike} ${pos.spread_type || ''}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'option_single') {
                desc = `${pos.option_type || ''} ${pos.strike}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'short_stock') {
                desc = 'Short';
            } else {
                desc = 'Stock';
            }

            const cost = pos.cost_basis != null ? `$${parseFloat(pos.cost_basis).toFixed(2)}` : '\u2014';
            const value = pos.current_value != null ? `$${parseFloat(pos.current_value).toFixed(2)}` : '\u2014';

            let pnlHtml = '\u2014';
            if (pos.unrealized_pnl != null) {
                const pnl = parseFloat(pos.unrealized_pnl);
                const pnlPct = pos.unrealized_pnl_pct != null ? ` (${parseFloat(pos.unrealized_pnl_pct).toFixed(1)}%)` : '';
                const cls = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
                const sign = pnl >= 0 ? '+' : '-';
                pnlHtml = `<span class="${cls}">${sign}$${Math.abs(pnl).toFixed(2)}${pnlPct}</span>`;
            }

            html += `<tr>
                <td><strong>${escapeHtml(pos.ticker)}</strong></td>
                <td>${escapeHtml(desc)}</td>
                <td>${pos.quantity}</td>
                <td>${cost}</td>
                <td>${value}</td>
                <td>${pnlHtml}</td>
            </tr>`;
        }

        tbody.innerHTML = html;
    } catch (err) {
        console.error('Failed to load positions:', err);
    }
}

function formatExpiry(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getMonth()+1}/${d.getDate()}`;
}

setInterval(loadPortfolioBalances, 60000);
// Portfolio positions 60s poll removed (Phase 0D) — redundant with 30s v2 position refresh


// Display effective bias when hierarchical modifier is applied
function updateEffectiveBias(timeframe, rawLevel, effectiveLevel, modifierDetails) {
    const container = document.getElementById(`${timeframe}Bias`);
    const effectiveEl = document.getElementById(`${timeframe}Effective`);
    
    if (!effectiveEl) return;
    
    const levelEl = effectiveEl.querySelector('.effective-level');
    if (levelEl) {
        levelEl.textContent = effectiveLevel.replace('_', ' ');
        
        // Determine if it's a boost or drag
        const rawValue = getBiasValue(rawLevel);
        const effectiveValue = getBiasValue(effectiveLevel);
        
        levelEl.classList.remove('boost', 'drag');
        if (effectiveValue > rawValue) {
            levelEl.classList.add('boost');
        } else if (effectiveValue < rawValue) {
            levelEl.classList.add('drag');
        }
    }
    
    // Show the effective display
    effectiveEl.style.display = 'flex';
    
    // Add modifier indicator to card
    if (container) {
        container.classList.add('has-modifier');
        container.classList.remove('modifier-boost', 'modifier-drag');
        
        const rawValue = getBiasValue(rawLevel);
        const effectiveValue = getBiasValue(effectiveLevel);
        if (effectiveValue > rawValue) {
            container.classList.add('modifier-boost');
        } else if (effectiveValue < rawValue) {
            container.classList.add('modifier-drag');
        }
    }
    
    // Add tooltip with modifier details if available
    if (modifierDetails && effectiveEl) {
        const reason = modifierDetails.adjustment_reason || 'hierarchical modifier';
        const modifierName = modifierDetails.modifier_name || 'higher timeframe';
        effectiveEl.title = `Modified by ${modifierName}: ${reason.replace(/_/g, ' ')}`;
    }
}

// Hide effective bias display
function hideEffectiveBias(timeframe) {
    const effectiveEl = document.getElementById(`${timeframe}Effective`);
    const container = document.getElementById(`${timeframe}Bias`);
    
    if (effectiveEl) {
        effectiveEl.style.display = 'none';
    }
    
    if (container) {
        container.classList.remove('has-modifier', 'modifier-boost', 'modifier-drag');
    }
}

// Convert bias level to numeric value for comparison
function getBiasValue(level) {
    const values = {
        // New 6-level system
        'MAJOR_TORO': 6, 'MAJOR TORO': 6,
        'MINOR_TORO': 5, 'MINOR TORO': 5,
        'LEAN_TORO': 4, 'LEAN TORO': 4,
        'LEAN_URSA': 3, 'LEAN URSA': 3,
        'MINOR_URSA': 2, 'MINOR URSA': 2,
        'MAJOR_URSA': 1, 'MAJOR URSA': 1,
        // Legacy mappings
        'TORO_MAJOR': 6, 'TORO MAJOR': 6,
        'TORO_MINOR': 5, 'TORO MINOR': 5,
        'NEUTRAL': 4,  // Map to LEAN_TORO
        'URSA_MINOR': 2, 'URSA MINOR': 2,
        'URSA_MAJOR': 1, 'URSA MAJOR': 1
    };
    return values[level?.toUpperCase()?.replace('_', ' ')] || 4;  // Default LEAN_TORO
}

// Check if bias level is bullish (TORO-based)
function isBullishBias(level) {
    return level && (level.toUpperCase().includes('TORO') || getBiasValue(level) >= 4);
}

// Check if bias level is bearish (URSA-based)
function isBearishBias(level) {
    return level && (level.toUpperCase().includes('URSA') || getBiasValue(level) <= 3);
}

// Check and apply alignment styling when Cyclical and Weekly are aligned
function checkAndApplyBiasAlignment() {
    const container = document.querySelector('.container');
    const alignmentIndicator = document.getElementById('biasAlignmentIndicator');
    const alignmentText = document.getElementById('alignmentText');
    
    if (!container) return;
    
    // Remove existing alignment classes
    container.classList.remove('bias-aligned-bullish', 'bias-aligned-bearish');
    
    // Get current bias levels
    const cyclicalLevel = cyclicalBiasFullData?.level || '';
    const weeklyLevel = weeklyBiasFullData?.level || '';
    
    const alignment = getBiasAlignmentStatus(cyclicalLevel, weeklyLevel);

    if (alignment.alignmentClass) {
        container.classList.add(alignment.alignmentClass);
    }

    if (alignmentText) alignmentText.textContent = alignment.alignmentText;
}

// Check and display crisis alert when tiered factors are in crisis mode
function checkAndDisplayCrisisAlert(cyclicalData) {
    const crisisBanner = document.getElementById('crisisAlertBanner');
    const crisisFactorsEl = document.getElementById('crisisFactors');
    
    if (!crisisBanner) return;
    
    // Check if crisis mode is active from the cyclical data
    const details = cyclicalData?.details || {};
    const crisisActive = details.crisis_mode_active || false;
    const factors = details.factors || {};
    
    if (crisisActive) {
        // Find which factors are in crisis tier
        const crisisFactorNames = [];
        
        Object.keys(factors).forEach(factorName => {
            const factorData = factors[factorName];
            const tier = factorData?.details?.tier || 'standard';
            
            if (tier.startsWith('crisis')) {
                // Convert factor name to readable format
                const readableName = factorName
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
                
                const status = factorData?.details?.status || tier;
                crisisFactorNames.push(`${readableName} (${status})`);
            }
        });
        
        if (crisisFactorNames.length > 0) {
            crisisFactorsEl.textContent = crisisFactorNames.join(', ');
            crisisBanner.classList.add('active');
            crisisBanner.style.display = 'flex';
            console.warn('CRISIS MODE ACTIVE:', crisisFactorNames);
        }
    } else {
        // No crisis - hide the banner
        crisisBanner.classList.remove('active');
        crisisBanner.style.display = 'none';
    }
}

// Savita Indicator Update Functions (Optional - bonus factor when BofA data available)
function checkSavitaStatus(cyclicalData) {
    const btn = document.getElementById('savitaUpdateBtn');
    if (!btn) return;
    
    const factors = cyclicalData?.details?.factors || {};
    const savitaData = factors.savita_indicator?.details || {};
    
    // Check Savita freshness
    const lastUpdated = savitaData.last_updated || savitaData.reading?.last_updated;
    
    if (!lastUpdated) {
        // No Savita data - just show normal button
        btn.classList.remove('stale');
        btn.title = 'Add Savita Indicator (optional)';
        return;
    }
    
    // Check if data is stale (>30 days old)
    const updateDate = new Date(lastUpdated);
    const now = new Date();
    const daysSinceUpdate = Math.floor((now - updateDate) / (1000 * 60 * 60 * 24));
    
    if (daysSinceUpdate > 30) {
        // Stale - add pulse animation
        btn.classList.add('stale');
        btn.title = `Savita inactive (${daysSinceUpdate}d old) - click to update`;
    } else if (daysSinceUpdate > 20) {
        // Getting stale soon
        btn.classList.add('stale');
        btn.title = `Savita getting stale (${daysSinceUpdate}d) - consider updating`;
    } else {
        // Fresh and active
        btn.classList.remove('stale');
        btn.title = `Savita active (updated ${daysSinceUpdate}d ago)`;
    }
}

function initSavitaUpdateModal() {
    const updateBtn = document.getElementById('savitaUpdateBtn');
    const modal = document.getElementById('savitaUpdateModal');
    const closeBtn = document.getElementById('closeSavitaModal');
    const cancelBtn = document.getElementById('cancelSavitaUpdate');
    const submitBtn = document.getElementById('submitSavitaUpdate');
    
    if (!modal) return;
    
    // Open modal from new button
    if (updateBtn) {
        updateBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            openSavitaModal();
        });
    }
    
    async function openSavitaModal() {
        // Fetch current Savita status
        try {
            const response = await fetch(`${API_URL}/bias-auto/savita`);
            const result = await response.json();
            
            if (result.status === 'success') {
                const data = result.data;
                document.getElementById('savitaCurrentReading').textContent = data.reading || '--';
                document.getElementById('savitaLastUpdated').textContent = data.last_updated || '--';
                
                // Check if stale
                const currentInfo = document.getElementById('savitaCurrentInfo');
                if (data.last_updated) {
                    const daysSince = Math.floor((new Date() - new Date(data.last_updated)) / (1000 * 60 * 60 * 24));
                    if (daysSince > 30) {
                        currentInfo.classList.add('stale');
                        currentInfo.innerHTML = `<strong>DISABLED (${daysSince}d old)</strong> - Savita not affecting score until updated`;
                    } else {
                        currentInfo.classList.remove('stale');
                    }
                }
            }
        } catch (error) {
            console.error('Error fetching Savita status:', error);
        }
        
        modal.classList.add('active');
    }
    
    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
        document.getElementById('savitaReading').value = '';
        document.getElementById('savitaDate').value = '';
    };
    
    closeBtn?.addEventListener('click', closeModal);
    cancelBtn?.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Submit update
    submitBtn?.addEventListener('click', async () => {
        const reading = parseFloat(document.getElementById('savitaReading').value);
        const date = document.getElementById('savitaDate').value;
        
        if (isNaN(reading) || reading < 40 || reading > 70) {
            alert('Please enter a valid reading between 40 and 70');
            return;
        }
        
        try {
            let url = `${API_URL}/bias-auto/savita/update?reading=${reading}`;
            if (date) url += `&date=${date}`;
            
            const response = await fetch(url, { method: 'POST', headers: { 'X-API-Key': API_KEY } });
            const result = await response.json();

            if (result.status === 'success') {
                alert(`Savita updated to ${reading}%`);
                closeModal();
                
                // Refresh bias data and update button style
                await loadBiasData();
                updateSavitaButtonStatus();
            } else {
                alert('Error updating Savita: ' + (result.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error updating Savita:', error);
            alert('Error updating Savita');
        }
    });
}

// Update Savita button style based on data freshness
function updateSavitaButtonStatus() {
    const btn = document.getElementById('savitaUpdateBtn');
    if (!btn) return;
    
    // Check if Savita data is stale (could be enhanced with actual data check)
    // For now, remove stale class after update
    btn.classList.remove('stale');
}

function updateBiasWithTrend(timeframe, biasData) {
    const container = document.getElementById(`${timeframe}Bias`);
    const levelElement = document.getElementById(`${timeframe}Level`);
    const detailsElement = document.getElementById(`${timeframe}Details`);
    
    if (!biasData) {
        if (detailsElement) detailsElement.textContent = 'Awaiting first refresh';
        return;
    }
    
    const rawLevel = biasData.level || 'LEAN_TORO';
    const trend = biasData.trend || 'NEW';
    const previousLevel = biasData.previous_level;
    const timestamp = biasData.timestamp;
    
    // Apply personal bias adjustment if enabled for this timeframe
    let level = rawLevel;
    let personalBiasApplied = false;
    if (personalBias !== 'NEUTRAL' && personalBiasAppliesTo[timeframe]) {
        const rawValue = getBiasValue(rawLevel);
        let adjustedValue = rawValue;
        
        if (personalBias === 'TORO') {
            adjustedValue = Math.min(6, rawValue + 1);
        } else if (personalBias === 'URSA') {
            adjustedValue = Math.max(1, rawValue - 1);
        }
        
        if (adjustedValue !== rawValue) {
            const levelMap = {6: 'MAJOR_TORO', 5: 'MINOR_TORO', 4: 'LEAN_TORO', 3: 'LEAN_URSA', 2: 'MINOR_URSA', 1: 'MAJOR_URSA'};
            level = levelMap[adjustedValue] || rawLevel;
            personalBiasApplied = true;
        }
    }
    
    // Update level display (preserve shift indicator if it exists, only for weekly)
    if (levelElement) {
        const shiftIndicator = (timeframe === 'weekly') ? levelElement.querySelector('.bias-shift-indicator') : null;
        levelElement.textContent = level.replace('_', ' ');
        levelElement.className = `bias-level ${level}`;
        // Re-add shift indicator if it existed (for weekly bias)
        if (shiftIndicator && timeframe === 'weekly') {
            levelElement.appendChild(shiftIndicator);
        }
    }
    
    // Update container styling
    if (container) {
        container.classList.remove('bullish', 'bearish', 'neutral');
        if (level.includes('TORO')) {
            container.classList.add('bullish');
        } else if (level.includes('URSA')) {
            container.classList.add('bearish');
        } else {
            container.classList.add('bullish');  // Default bullish in 6-level system
        }
    }
    
    // Update details with trend
    if (detailsElement) {
        let trendIcon = '';
        let trendText = '';
        
        switch (trend) {
            case 'IMPROVING':
                trendIcon = '&uarr;';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'DECLINING':
                trendIcon = '&darr;';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'STABLE':
                trendIcon = '&rarr;';
                trendText = 'unchanged';
                break;
            default:
                trendIcon = '&bull;';
                trendText = 'first reading';
        }
        
        // Format timestamp in Eastern Time (market hours)
        let timeStr = '';
        if (timestamp) {
            const date = new Date(timestamp);
            timeStr = date.toLocaleString('en-US', { 
                timeZone: 'America/New_York',
                month: 'short', 
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit'
            }) + ' ET';
        }
        
        const details = biasData?.details || {};
        const totalVote = Number.isFinite(Number(details.total_vote)) ? Number(details.total_vote) : null;
        const maxVote =
            Number.isFinite(Number(details.max_possible))
                ? Number(details.max_possible)
                : Number.isFinite(Number(details.max_possible_current))
                    ? Number(details.max_possible_current)
                    : Number.isFinite(Number(details.max_possible_normal))
                        ? Number(details.max_possible_normal)
                        : null;
        const factorCount = details.factors && typeof details.factors === 'object'
            ? Object.keys(details.factors).length
            : null;
        const source = details.source || null;

        const metaParts = [];
        if (totalVote !== null && maxVote !== null) metaParts.push(`vote ${totalVote}/${maxVote}`);
        if (factorCount !== null) metaParts.push(`${factorCount} factors`);
        if (source) metaParts.push(source.replaceAll('_', ' '));

        detailsElement.innerHTML = `
            <span class="trend-indicator trend-${trend.toLowerCase()}">${trendIcon}</span> ${trendText}
            ${metaParts.length ? `<br><small>${metaParts.join(' | ')}</small>` : ''}
            ${timeStr ? `<br><small>Updated: ${timeStr}</small>` : ''}
        `;
    }
}

// Update weekly bias with factor filtering
function updateWeeklyBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        // Fallback to regular update if no factor data
        updateBiasWithTrend('weekly', biasData);
        return;
    }
    
    // Preserve shift indicator before updating
    const weeklyLevelElement = document.getElementById('weeklyLevel');
    const shiftIndicator = weeklyLevelElement ? weeklyLevelElement.querySelector('.bias-shift-indicator') : null;
    
    // Calculate filtered vote total
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (weeklyBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(7 * scaleFactor);
    const minorThreshold = Math.round(3 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    // Create modified bias data for display
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    // Update display
    updateBiasWithTrend('weekly', modifiedBiasData);
    
    // Re-add shift indicator if it existed
    if (shiftIndicator && weeklyLevelElement) {
        weeklyLevelElement.appendChild(shiftIndicator);
    }
    
    // Show/hide warning badge
    updateWarningBadge(enabledCount, 'weekly', totalFactors);
}



// Update warning badge for any timeframe
function updateWarningBadge(enabledCount, timeframe = 'weekly', totalFactorsOverride = null) {
    const levelElement = document.getElementById(`${timeframe}Level`);
    if (!levelElement) return;
    
    // Remove existing warning badge
    const existingBadge = levelElement.querySelector('.bias-warning-badge');
    if (existingBadge) {
        existingBadge.remove();
    }
    
    const totalFactors = Number.isFinite(totalFactorsOverride) && totalFactorsOverride > 0
        ? totalFactorsOverride
        : Math.max(1, getConfiguredFactorCount(timeframe));

    // Add warning if not all factors enabled
    if (enabledCount < totalFactors) {
        const badge = document.createElement('span');
        badge.className = 'bias-warning-badge';
        badge.textContent = '!';
        badge.title = `${enabledCount} of ${totalFactors} factors active`;
        levelElement.appendChild(badge);
    }
}

function getConfiguredFactorCount(timeframe) {
    if (timeframe === 'daily') return Object.keys(dailyBiasFactorStates).length;
    if (timeframe === 'cyclical') return Object.keys(cyclicalBiasFactorStates).length;
    return Object.keys(weeklyBiasFactorStates).length;
}

// Update Daily Bias with factor filtering
function updateDailyBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        updateBiasWithTrend('daily', biasData);
        return;
    }
    
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (dailyBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(8 * scaleFactor);
    const minorThreshold = Math.round(4 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    updateBiasWithTrend('daily', modifiedBiasData);
    updateWarningBadge(enabledCount, 'daily', totalFactors);
}

// Update Cyclical Bias with factor filtering
function updateCyclicalBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        updateBiasWithTrend('cyclical', biasData);
        return;
    }
    
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (cyclicalBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(7 * scaleFactor);
    const minorThreshold = Math.round(3 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    updateBiasWithTrend('cyclical', modifiedBiasData);
    updateWarningBadge(enabledCount, 'cyclical', totalFactors);
}

// =========================================================================
// PERSONAL BIAS & OVERRIDE CONTROLS
// =========================================================================

function initPersonalBiasControls() {
    const personalBiasSelector = document.getElementById('personalBiasSelector');
    const overrideToggle = document.getElementById('biasOverrideToggle');
    const overrideDirectionSelector = document.getElementById('overrideDirectionSelector');
    const biasSection = document.querySelector('.bias-section');
    
    if (!personalBiasSelector || !overrideToggle) {
        console.warn('Personal bias control elements not found');
        return;
    }
    
    // Load saved states from localStorage
    loadPersonalBiasState();
    
    // Personal Bias Selector
    personalBiasSelector.addEventListener('change', (e) => {
        personalBias = e.target.value;
        savePersonalBiasState();
        
        // Re-render bias cards with new personal bias applied
        reRenderBiasCardsWithPersonalBias();
        
        // Update badges and alignment styling
        applyPersonalBiasToCards();
        checkBiasAlignment();
        
        console.log(`Personal bias set to: ${personalBias}`);
    });
    
    // Override Toggle
    overrideToggle.addEventListener('click', () => {
        biasOverrideActive = !biasOverrideActive;
        overrideToggle.dataset.active = biasOverrideActive.toString();
        overrideToggle.textContent = biasOverrideActive ? 'ON' : 'OFF';
        overrideDirectionSelector.disabled = !biasOverrideActive;
        
        // Update override direction data attribute
        const isBullish = biasOverrideDirection.includes('TORO');
        overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        
        // Update UI state - apply override styling to container
        applyOverrideStyling();
        
        // Update override banner
        updateOverrideBanner();
        
        savePersonalBiasState();
        
        // Re-render signals with new bias state
        if (typeof renderSignals === 'function') {
            refreshSignalViews();
        }
        
        console.log(`Bias override: ${biasOverrideActive ? 'ACTIVE' : 'INACTIVE'} - ${biasOverrideDirection}`);
    });
    
    // Override Direction Selector
    overrideDirectionSelector.addEventListener('change', (e) => {
        biasOverrideDirection = e.target.value;
        
        // Update override toggle direction attribute
        const isBullish = biasOverrideDirection.includes('TORO');
        overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        
        // Update styling
        applyOverrideStyling();
        updateOverrideBanner();
        savePersonalBiasState();
        
        // Re-render signals with new bias
        if (typeof renderSignals === 'function') {
            refreshSignalViews();
        }
        
        console.log(`Override direction set to: ${biasOverrideDirection}`);
    });
    
    // Apply initial state
    applyPersonalBiasToCards();
    applyOverrideStyling();
    updateOverrideBanner();
}

// Apply override styling to container and all sections
function applyOverrideStyling() {
    const container = document.querySelector('.container');
    if (!container) return;
    
    // Remove existing override classes
    container.classList.remove('override-active-bullish', 'override-active-bearish');
    
    // Also remove from body for wider support
    document.body.classList.remove('override-active-bullish', 'override-active-bearish');
    
    if (biasOverrideActive) {
        const isBullish = biasOverrideDirection.includes('TORO');
        const overrideClass = isBullish ? 'override-active-bullish' : 'override-active-bearish';
        container.classList.add(overrideClass);
        document.body.classList.add(overrideClass);
        console.log(`Override styling applied: ${overrideClass}`);
    } else {
        console.log('Override styling removed');
    }
}

function loadPersonalBiasState() {
    try {
        const saved = localStorage.getItem('personalBiasState');
        if (saved) {
            const state = JSON.parse(saved);
            personalBias = state.personalBias || 'NEUTRAL';
            biasOverrideActive = state.biasOverrideActive || false;
            biasOverrideDirection = state.biasOverrideDirection || 'MAJOR_TORO';
            
            // Load per-timeframe personal bias toggles
            if (state.personalBiasAppliesTo) {
                personalBiasAppliesTo = {
                    daily: state.personalBiasAppliesTo.daily !== false,
                    weekly: state.personalBiasAppliesTo.weekly !== false,
                    cyclical: state.personalBiasAppliesTo.cyclical !== false
                };
            }
        }
        
        // Apply to UI elements
        const personalBiasSelector = document.getElementById('personalBiasSelector');
        const overrideToggle = document.getElementById('biasOverrideToggle');
        const overrideDirectionSelector = document.getElementById('overrideDirectionSelector');
        const biasSection = document.querySelector('.bias-section');
        
        if (personalBiasSelector) personalBiasSelector.value = personalBias;
        if (overrideToggle) {
            overrideToggle.dataset.active = biasOverrideActive.toString();
            overrideToggle.textContent = biasOverrideActive ? 'ON' : 'OFF';
            // Set direction attribute for styling
            const isBullish = biasOverrideDirection.includes('TORO');
            overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        }
        if (overrideDirectionSelector) {
            overrideDirectionSelector.value = biasOverrideDirection;
            overrideDirectionSelector.disabled = !biasOverrideActive;
        }
        if (biasSection) {
            biasSection.classList.toggle('override-active', biasOverrideActive);
        }
        
        // Apply override styling to container
        applyOverrideStyling();
        
    } catch (e) {
        console.error('Error loading personal bias state:', e);
    }
}

function savePersonalBiasState() {
    try {
        localStorage.setItem('personalBiasState', JSON.stringify({
            personalBias,
            biasOverrideActive,
            biasOverrideDirection,
            personalBiasAppliesTo
        }));
    } catch (e) {
        console.error('Error saving personal bias state:', e);
    }
}

function reRenderBiasCardsWithPersonalBias() {
    // Re-render all bias cards from cached data with new personal bias applied
    // This avoids an API call - just re-renders with existing data
    
    if (dailyBiasFullData) {
        if (dailyBiasFullData.details && dailyBiasFullData.details.factors) {
            updateDailyBiasWithFactors(dailyBiasFullData);
        } else {
            updateBiasWithTrend('daily', dailyBiasFullData);
        }
    }
    
    if (weeklyBiasFullData) {
        if (weeklyBiasFullData.details && weeklyBiasFullData.details.factors) {
            updateWeeklyBiasWithFactors(weeklyBiasFullData);
        } else {
            updateBiasWithTrend('weekly', weeklyBiasFullData);
        }
    }
    
    if (cyclicalBiasFullData) {
        if (cyclicalBiasFullData.details && cyclicalBiasFullData.details.factors) {
            updateCyclicalBiasWithFactors(cyclicalBiasFullData);
        } else {
            updateBiasWithTrend('cyclical', cyclicalBiasFullData);
        }
    }
    
    console.log('Bias cards re-rendered with personal bias adjustment');
}

function applyPersonalBiasToCards() {
    // Remove existing badges
    document.querySelectorAll('.personal-bias-badge').forEach(b => b.remove());
    
    if (personalBias === 'NEUTRAL') return;
    
    // Add badge to each bias card where personal bias is enabled for that timeframe
    const timeframeMap = {
        'dailyBias': 'daily',
        'weeklyBias': 'weekly',
        'cyclicalBias': 'cyclical'
    };
    
    Object.entries(timeframeMap).forEach(([cardId, timeframe]) => {
        // Only add badge if personal bias is enabled for this timeframe
        if (!personalBiasAppliesTo[timeframe]) return;
        
        const card = document.getElementById(cardId);
        if (!card) return;
        
        const biasLevel = card.querySelector('.bias-level');
        const biasDetails = card.querySelector('.bias-details');
        
        if (biasLevel && biasDetails) {
            const badge = document.createElement('div');
            badge.className = `personal-bias-badge ${personalBias.toLowerCase()}`;
            badge.textContent = personalBias === 'TORO' ? '+1 Personal Bias' : '-1 Personal Bias';
            badge.title = `Your personal ${personalBias} bias adds ${personalBias === 'TORO' ? '+1' : '-1'} to the score`;
            
            // Insert after bias-level (and bias-effective if present)
            const biasEffective = card.querySelector('.bias-effective');
            const insertAfter = biasEffective || biasLevel;
            insertAfter.parentNode.insertBefore(badge, insertAfter.nextSibling);
        }
    });
}

function updateOverrideBanner() {
    const banner = document.getElementById('overrideActiveBanner');
    const biasDisplay = document.getElementById('overrideBiasDisplay');
    
    if (banner && biasDisplay) {
        biasDisplay.textContent = biasOverrideDirection.replace('_', ' ');
    }
}

/**
 * Get the effective bias for trade filtering
 * When override is active, returns the override direction
 * Otherwise, returns the calculated bias with personal bias modifier
 */
function getEffectiveTradingBias() {
    if (biasOverrideActive) {
        return {
            level: biasOverrideDirection,
            isOverride: true,
            personalBias: personalBias
        };
    }
    
    // Get current daily bias (or use LEAN_TORO if not loaded - bullish default)
    const dailyLevel = dailyBiasFullData?.level || 'LEAN_TORO';
    const weeklyLevel = weeklyBiasFullData?.level || 'LEAN_TORO';
    const cyclicalLevel = cyclicalBiasFullData?.level || 'LEAN_TORO';
    
    // Calculate composite score
    let compositeScore = getBiasValue(dailyLevel);
    
    // Add personal bias modifier
    if (personalBias === 'TORO') {
        compositeScore += 1;
    } else if (personalBias === 'URSA') {
        compositeScore -= 1;
    }
    
    // Clamp to valid range [1, 6]
    compositeScore = Math.max(1, Math.min(6, compositeScore));
    
    // Convert back to level name (6-level system)
    const levelMap = {6: 'MAJOR_TORO', 5: 'MINOR_TORO', 4: 'LEAN_TORO', 3: 'LEAN_URSA', 2: 'MINOR_URSA', 1: 'MAJOR_URSA'};
    const effectiveLevel = levelMap[compositeScore] || 'LEAN_TORO';
    
    return {
        level: effectiveLevel,
        rawDaily: dailyLevel,
        rawWeekly: weeklyLevel,
        rawCyclical: cyclicalLevel,
        isOverride: false,
        personalBias: personalBias,
        personalModifier: personalBias === 'NEUTRAL' ? 0 : (personalBias === 'TORO' ? 1 : -1)
    };
}

/**
 * Check if a trade signal aligns with current bias
 * Used by Trade Ideas filtering
 */
function isSignalAlignedWithBias(signalDirection) {
    const bias = getEffectiveTradingBias();
    const biasValue = getBiasValue(bias.level);
    
    if (signalDirection === 'LONG') {
        // LONG signals align with bullish bias (TORO levels: >= 4)
        return biasValue >= 4;
    } else if (signalDirection === 'SHORT') {
        // SHORT signals align with bearish bias (URSA levels: <= 3)
        return biasValue <= 3;
    }
    
    return true; // Unknown direction, allow
}



// fetchBiasShiftStatus + updateBiasShiftDisplay removed (Phase 0D)
// bias-auto/shift-status endpoint no longer exists. Shift data comes from composite.

async function loadBiasDataFallback() {
    // Fallback to old endpoints if scheduler not available
    const timeframes = ['DAILY', 'WEEKLY'];
    
    for (const timeframe of timeframes) {
        try {
            const response = await fetch(`${API_URL}/bias/${timeframe}`);
            const data = await response.json();
            
            const tfLower = timeframe.toLowerCase();
            const container = document.getElementById(`${tfLower}Bias`);
            const levelElement = document.getElementById(`${tfLower}Level`);
            const detailsElement = document.getElementById(`${tfLower}Details`);
            
            if (levelElement) {
                const level = data.level || 'LEAN_TORO';
                levelElement.textContent = level.replace('_', ' ');
                
                if (container) {
                    container.classList.remove('bullish', 'bearish', 'neutral');
                    if (level.includes('TORO')) {
                        container.classList.add('bullish');
                    } else if (level.includes('URSA')) {
                        container.classList.add('bearish');
                    } else {
                        container.classList.add('bullish');  // Default to bullish in 6-level system
                    }
                }
            }
            
            if (detailsElement) {
                detailsElement.textContent = 'TICK: N/A';
            }
        } catch (error) {
            console.error(`Error loading ${timeframe} bias:`, error);
        }
    }
    
    // Load Cyclical separately (fallback)
    await loadCyclicalBiasFallback();
}

async function loadCyclicalBiasFallback() {
    // bias-auto/CYCLICAL endpoint removed (Phase 0D). Cyclical data comes from timeframe cards.
    return;
}



// Signal Rendering — unified feed (exclude raw crypto, keep equity tickers like IBIT)
function renderSignals() {
    const container = document.getElementById('tradeSignals');

    // Show all equity signals; exclude asset_class=CRYPTO (raw crypto pairs)
    const allSignals = signals.equity
        .sort((a, b) => (b.score || 0) - (a.score || 0));

    if (allSignals.length === 0) {
        container.innerHTML = '<p class="empty-state">No trade ideas</p>';
        return;
    }

    const pagination = tradeIdeasPagination.equity;
    const loadMoreText = pagination?.loading ? 'Loading...' : 'Reload previous';
    const loadMoreDisabled = pagination?.loading ? 'disabled' : '';
    const loadMoreButton = pagination?.hasMore
        ? `<div class="trade-ideas-footer">
                <button class="reload-previous-btn" ${loadMoreDisabled}>${loadMoreText}</button>
           </div>`
        : '';

    container.innerHTML = allSignals.map(signal => createSignalCard(signal)).join('') + loadMoreButton;

    attachSignalActions();
    attachReloadPreviousHandler();
    attachDynamicKbHandlers(container);
}

function getCryptoFilterState() {
    const enabledStrategies = new Set();
    document.querySelectorAll('.crypto-strategy-cb:checked').forEach(cb => {
        enabledStrategies.add(cb.dataset.strategy);
    });
    const allowLong = document.getElementById('cryptoFilterLong')?.checked !== false;
    const allowShort = document.getElementById('cryptoFilterShort')?.checked !== false;
    const minScore = parseInt(document.getElementById('cryptoScoreThreshold')?.value || '1', 10);
    return { enabledStrategies, allowLong, allowShort, minScore };
}

function renderCryptoSignals() {
    const container = document.getElementById('cryptoSignalsList');
    if (!container) return;

    const sortBy = document.getElementById('cryptoSignalSort')?.value || 'score';
    const filters = getCryptoFilterState();
    let cryptoSignals = [...signals.crypto];

    // Apply strategy filters
    cryptoSignals = cryptoSignals.filter(s => {
        const strategy = (s.strategy || '').toLowerCase().replace(/[\s-]/g, '_');
        if (filters.enabledStrategies.size > 0) {
            let matched = false;
            for (const enabled of filters.enabledStrategies) {
                // Exact match OR strategy is a versioned variant (e.g. "golden_touch_v2")
                // Use prefix check so partial checkbox keys like "touch" don't match "golden_touch"
                if (strategy === enabled || strategy.startsWith(enabled + '_')) {
                    matched = true;
                    break;
                }
            }
            if (!matched) return false;
        }
        const dir = (s.direction || '').toUpperCase();
        if (dir === 'LONG' && !filters.allowLong) return false;
        if (dir === 'SHORT' && !filters.allowShort) return false;
        if ((s.score || 0) < filters.minScore) return false;
        return true;
    });

    // Apply score decay for stale signals (-5 per 5-min block after 15 min)
    const now = Date.now();
    cryptoSignals = cryptoSignals.map(s => {
        let timeStr = s.timestamp || s.created_at || '';
        if (timeStr && !timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
            timeStr += 'Z';
        }
        const created = timeStr ? new Date(timeStr).getTime() : 0;
        const ageMinutes = created ? (now - created) / 60000 : 0;
        if (ageMinutes > 15) {
            const decayBlocks = Math.floor((ageMinutes - 15) / 5);
            const decay = decayBlocks * 5;
            return { ...s, display_score: Math.max(0, (s.score || 0) - decay) };
        }
        return { ...s, display_score: s.score || 0 };
    });

    if (cryptoSignals.length === 0) {
        container.innerHTML = '<p class="empty-state">No crypto signals match filters</p>';
        return;
    }

    cryptoSignals.sort((a, b) => {
        const rankA = getCryptoSignalPriority(a);
        const rankB = getCryptoSignalPriority(b);
        if (rankA !== rankB) {
            return rankB - rankA;
        }
        if (sortBy === 'recency') {
            const timeA = new Date(a.timestamp || a.created_at || 0).getTime();
            const timeB = new Date(b.timestamp || b.created_at || 0).getTime();
            return timeB - timeA;
        }
        return (Number(b.display_score) || 0) - (Number(a.display_score) || 0);
    });

    container.innerHTML = cryptoSignals.map(signal => createCryptoSignalCard(signal)).join('');

    // Also update crypto positions
    renderCryptoPositions();
}

async function loadGroupedSignals() {
    try {
        const response = await fetch(`${API_URL}/trade-ideas/grouped`);
        const data = await response.json();
        if (data.groups) {
            renderGroupedSignals(data.groups);
        }
    } catch (error) {
        console.warn('Grouped signals failed, falling back to flat view:', error);
        renderSignals();
    }
}

function renderGroupedSignals(groups) {
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    if (!groups || groups.length === 0) {
        container.innerHTML = '<p class="empty-state">No trade ideas</p>';
        return;
    }

    container.innerHTML = groups.map(group => {
        const signal = group.primary_signal;
        const isConviction = group.confluence_tier === 'CONVICTION';
        const isConfirmed = group.confluence_tier === 'CONFIRMED';
        const confluenceBadge = isConviction
            ? '<span class="confluence-badge conviction">CONVICTION</span>'
            : isConfirmed
            ? '<span class="confluence-badge confirmed">CONFIRMED</span>'
            : '';
        const signalCountBadge = group.signal_count > 1
            ? `<span class="signal-count-badge">${group.signal_count} signals</span>`
            : '';
        const category = (signal.signal_category || 'TRADE_SETUP');

        // Position overlap check
        let positionBadge = '';
        const matchingPos = openPositions.find(p =>
            (p.ticker || '').toUpperCase() === group.ticker
        );
        if (matchingPos) {
            const posDir = (matchingPos.direction || '').toUpperCase();
            const sigDir = group.direction.toUpperCase();
            const aligns = (posDir === sigDir) ||
                (posDir === 'BEARISH' && sigDir === 'SHORT') ||
                (posDir === 'SHORT' && sigDir === 'BEARISH') ||
                (posDir === 'BULLISH' && sigDir === 'LONG') ||
                (posDir === 'LONG' && sigDir === 'BULLISH');
            positionBadge = aligns
                ? `<span class="position-overlap confirms">Confirms ${matchingPos.ticker} position</span>`
                : `<span class="position-overlap counters">Counters ${matchingPos.ticker} position</span>`;
        }

        // Stale badge
        let staleBadge = '';
        if (group.newest_at) {
            try {
                const mins = Math.round((Date.now() - new Date(group.newest_at).getTime()) / 60000);
                if (mins > 120) staleBadge = '<span class="stale-badge">Stale</span>';
            } catch(e) {}
        }

        const formatPrice = (val) => val ? parseFloat(val).toFixed(2) : '-';
        const formatRR = (val) => typeof formatRiskReward === 'function' ? formatRiskReward(val) : (val ? parseFloat(val).toFixed(1) + ':1' : '-');

        // Card content varies by signal_category
        let detailsHtml = '';
        if (category === 'FLOW_INTEL') {
            let meta = signal.metadata || {};
            if (typeof meta === 'string') { try { meta = JSON.parse(meta); } catch(e) {} }
            detailsHtml = `
                <div class="signal-details flow-details">
                    <div class="signal-detail"><div class="signal-detail-label">Premium</div><div class="signal-detail-value">$${formatLargeNumber(meta.total_premium)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">P/C</div><div class="signal-detail-value">${meta.pc_ratio || '-'}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Sentiment</div><div class="signal-detail-value">${meta.flow_sentiment || '-'}</div></div>
                </div>`;
        } else if (category === 'DARK_POOL') {
            let meta = signal.metadata || {};
            if (typeof meta === 'string') { try { meta = JSON.parse(meta); } catch(e) {} }
            detailsHtml = `
                <div class="signal-details">
                    <div class="signal-detail"><div class="signal-detail-label">POC</div><div class="signal-detail-value">${formatPrice(meta.poc)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Entry</div><div class="signal-detail-value">${formatPrice(signal.entry_price)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Stop</div><div class="signal-detail-value">${formatPrice(signal.stop_loss)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Target</div><div class="signal-detail-value">${formatPrice(signal.target_1)}</div></div>
                </div>`;
        } else {
            // Standard TRADE_SETUP card
            detailsHtml = `
                <div class="signal-details">
                    <div class="signal-detail"><div class="signal-detail-label">Entry</div><div class="signal-detail-value">${formatPrice(signal.entry_price)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Stop</div><div class="signal-detail-value">${formatPrice(signal.stop_loss)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Target</div><div class="signal-detail-value">${formatPrice(signal.target_1)}</div></div>
                </div>
                <div class="signal-details">
                    <div class="signal-detail"><div class="signal-detail-label">R:R</div><div class="signal-detail-value">${formatRR(signal.risk_reward)}</div></div>
                    <div class="signal-detail"><div class="signal-detail-label">Direction</div><div class="signal-detail-value direction-${(signal.direction || '').toLowerCase()}">${signal.direction || '-'}</div></div>
                </div>`;
        }

        // Related signals expandable section
        let relatedHtml = '';
        if (group.related_signals && group.related_signals.length > 0) {
            const relatedItems = group.related_signals.map(rs => {
                const ago = rs.timestamp ? getTimeAgo(rs.timestamp) : '';
                return `<div class="related-signal-row">
                    <span class="related-strategy">${formatStrategyName(rs.strategy)}</span>
                    <span class="related-score">${Math.round(rs.score)}</span>
                    <span class="related-time">${ago}</span>
                </div>`;
            }).join('');
            relatedHtml = `
                <div class="related-signals-toggle" onclick="this.nextElementSibling.classList.toggle('expanded')">
                    + ${group.related_signals.length} supporting signal${group.related_signals.length > 1 ? 's' : ''}
                </div>
                <div class="related-signals-panel">
                    ${relatedItems}
                </div>`;
        }

        const score = Math.round(signal.score_v2 || signal.score || 0);
        const scoreTier = score >= 85 ? 'CRITICAL' : score >= 75 ? 'HIGH' : score >= 55 ? 'MEDIUM' : 'LOW';
        const tierBorderClass = isConviction ? 'conviction-border' : isConfirmed ? 'confirmed-border' : '';
        const categoryIcon = '';

        return `
            <div class="signal-card grouped ${tierBorderClass}" data-signal-id="${signal.signal_id}" data-group-key="${group.group_key}" data-signal="${encodeURIComponent(JSON.stringify(signal))}">
                <div class="signal-header">
                    <div>
                        <div class="signal-type">${categoryIcon}${formatSignalType(signal.signal_type || signal.strategy)}</div>
                        <div class="signal-strategy">${group.strategies.map(formatStrategyName).join(' + ')}</div>
                    </div>
                    <div class="signal-ticker ticker-link" data-action="view-chart">${group.ticker}</div>
                </div>

                <div class="signal-badges">
                    ${confluenceBadge}${signalCountBadge}${positionBadge}${staleBadge}
                </div>

                <div class="signal-score-bar">
                    <div class="score-label">Score</div>
                    <div class="score-value ${scoreTier.toLowerCase()}">${score}</div>
                    <div class="score-tier ${scoreTier.toLowerCase()}">${scoreTier}</div>
                </div>

                ${detailsHtml}

                ${relatedHtml}

                <div class="signal-actions">
                    <button class="action-btn dismiss-btn" data-action="dismiss">Reject</button>
                    <button class="action-btn committee-btn" data-action="committee">Analyze</button>
                    ${category === 'FLOW_INTEL' ? '' : '<button class="action-btn select-btn" data-action="select">Accept</button>'}
                </div>
            </div>
        `;
    }).join('');

    attachSignalActions();
    attachDynamicKbHandlers(container);
}

function formatStrategyName(raw) {
    if (!raw) return 'Unknown';
    // Known display names
    const names = {
        'artemis': 'Artemis', 'hub_sniper': 'Artemis', 'hubsniper': 'Artemis',
        'phalanx': 'Phalanx', 'absorptionwall': 'Phalanx', 'absorption_wall': 'Phalanx',
        'scout': 'Scout Sniper', 'scout_sniper': 'Scout Sniper',
        'whale_hunter': 'Whale Hunter', 'whale': 'Whale Hunter',
        'uw_flow': 'UW Flow', 'sell_the_rip': 'Sell the Rip',
        'holy_grail': 'Holy Grail', 'holygrail': 'Holy Grail',
        'sniper': 'Sniper', 'exhaustion': 'Exhaustion',
    };
    const key = raw.toLowerCase().replace(/[\s-]+/g, '_');
    if (names[key]) return names[key];
    // Fallback: replace underscores/hyphens with spaces, title case
    return raw.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatSignalType(raw) {
    if (!raw) return 'Signal';
    const names = {
        'ARTEMIS_LONG': 'Artemis Long', 'ARTEMIS_SHORT': 'Artemis Short',
        'PHALANX_BULL': 'Phalanx Bull', 'PHALANX_BEAR': 'Phalanx Bear',
        'SCOUT_ALERT': 'Scout Alert',
        'WHALE_LONG': 'Whale Long', 'WHALE_SHORT': 'Whale Short',
        'WHALE_BULLISH': 'Whale Bullish', 'WHALE_BEARISH': 'Whale Bearish',
        'UW_FLOW_LONG': 'UW Flow Long', 'UW_FLOW_SHORT': 'UW Flow Short',
        'HOLY_GRAIL': 'Holy Grail', 'HOLY_GRAIL_1H': 'Holy Grail 1H', 'HOLY_GRAIL_15M': 'Holy Grail 15M',
        'SELL_RIP_EMA': 'Sell the Rip (EMA)', 'SELL_RIP_VWAP': 'Sell the Rip (VWAP)', 'SELL_RIP_EARLY': 'Sell the Rip (Early)',
        'SNIPER_URSA': 'Sniper Ursa', 'SNIPER_TAURUS': 'Sniper Taurus',
        'BULLISH_TRADE': 'Bullish Trade', 'BEAR_CALL': 'Bear Call',
        'APIS_CALL': 'Apis Call', 'KODIAK_CALL': 'Kodiak Call',
        'EXHAUSTION_TOP': 'Exhaustion Top', 'EXHAUSTION_BOTTOM': 'Exhaustion Bottom',
        'BULL_WALL': 'Phalanx Bull', 'BEAR_WALL': 'Phalanx Bear',
    };
    if (names[raw]) return names[raw];
    return raw.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatLargeNumber(n) {
    if (!n) return '-';
    n = parseFloat(n);
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
    return n.toFixed(0);
}

function getTimeAgo(timestamp) {
    try {
        const mins = Math.round((Date.now() - new Date(timestamp).getTime()) / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return mins + 'm ago';
        return Math.round(mins / 60) + 'h ago';
    } catch(e) { return ''; }
}

function refreshSignalViews() {
    // Use grouped view by default, fall back to flat
    loadGroupedSignals().catch(() => {
        if (typeof renderSignals === 'function') {
            renderSignals();
        }
    });
    renderCryptoSignals();
}

function createCryptoSignalCard(signal) {
    const displayScore = signal.display_score !== undefined ? signal.display_score : (signal.score || 0);
    const scoreStr = displayScore !== undefined && displayScore !== null ? Number(displayScore).toFixed(1) : '--';
    const scoreTier = typeof getScoreTier === 'function' ? getScoreTier(Number(displayScore) || 0) : 'MODERATE';
    const direction = signal.direction || 'N/A';
    const strategy = signal.strategy || 'Crypto Scanner';
    const formatPrice = (val) => val ? `$${parseFloat(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '--';

    // Parse enrichment data
    const enrichment = typeof signal.enrichment_data === 'string'
        ? JSON.parse(signal.enrichment_data || '{}') : (signal.enrichment_data || {});
    const ms = enrichment.market_structure || {};
    const sizing = enrichment.position_sizing || {};

    // Age indicator
    let timestampStr = '';
    let ageLabel = '';
    let ageClass = '';
    if (signal.timestamp || signal.created_at) {
        try {
            let timeStr = signal.timestamp || signal.created_at;
            if (!timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
                timeStr += 'Z';
            }
            const created = new Date(timeStr).getTime();
            timestampStr = new Date(timeStr).toLocaleString('en-US', {
                hour: 'numeric', minute: '2-digit', month: 'short', day: 'numeric'
            });
            const ageMin = Math.floor((Date.now() - created) / 60000);
            ageLabel = ageMin < 5 ? 'FRESH' : `${ageMin}m ago`;
            ageClass = ageMin < 5 ? 'fresh' : (ageMin >= 15 ? 'stale' : '');
        } catch (e) { /* ignore */ }
    }

    const badges = [];
    if (signal.signal_type === 'APIS_CALL') badges.push('<span class="crypto-badge apis">APIS</span>');
    if (signal.signal_type === 'KODIAK_CALL') badges.push('<span class="crypto-badge kodiak">KODIAK</span>');
    const strategyLower = (strategy || '').toLowerCase();
    if (strategyLower.includes('scout')) badges.push('<span class="crypto-badge scout">SCOUT</span>');
    if (strategyLower.includes('sniper')) badges.push('<span class="crypto-badge sniper">SNIPER</span>');
    if (strategyLower.includes('exhaustion')) badges.push('<span class="crypto-badge exhaustion">EXHAUST</span>');

    const biasAlignment = signal.bias_alignment || 'NEUTRAL';
    const isAligned = biasAlignment.includes('ALIGNED') && !biasAlignment.includes('COUNTER');
    const biasClass = isAligned ? 'aligned' : (biasAlignment.includes('COUNTER') ? 'counter' : '');
    const biasIcon = isAligned ? '&#10003;' : (biasAlignment.includes('COUNTER') ? '&#9888;' : '&#9675;');
    const biasText = biasAlignment.replace(/_/g, ' ');

    const signalTypeClass = signal.signal_type || '';

    // Market structure badge
    const msLabel = ms.context_label || '';
    const msBadgeHtml = msLabel ? `<span class="crypto-structure-badge ${msLabel.toLowerCase()}">${msLabel}<span class="structure-modifier">${ms.score_modifier > 0 ? '+' : ''}${ms.score_modifier || 0}</span></span>` : '';

    // Market structure detail row
    const msDetailHtml = (ms.poc || ms.cvd_direction || ms.book_imbalance) ? `
            <div class="crypto-signal-structure">
                <span><span class="crypto-signal-detail-label">POC</span> <span class="crypto-signal-detail-value">${ms.poc ? formatPrice(ms.poc) : '--'}</span></span>
                <span><span class="crypto-signal-detail-label">CVD</span> <span class="crypto-signal-detail-value ${(ms.cvd_direction || '').toLowerCase()}">${ms.cvd_direction || '--'}</span></span>
                <span><span class="crypto-signal-detail-label">Book</span> <span class="crypto-signal-detail-value">${ms.book_imbalance ? ms.book_imbalance.toFixed(2) + 'x' : '--'}</span></span>
            </div>` : '';

    // Breakout sizing row
    const sizingHtml = (sizing.contracts || sizing.leverage) ? `
            <div class="crypto-signal-sizing">
                <span><span class="crypto-signal-detail-label">Size</span> <span class="crypto-signal-detail-value">${sizing.contracts ? sizing.contracts.toFixed(4) + ' BTC' : '--'}</span></span>
                <span><span class="crypto-signal-detail-label">Leverage</span> <span class="crypto-signal-detail-value ${sizing.safe === false ? 'danger' : ''}">${sizing.leverage ? sizing.leverage.toFixed(1) + 'x' : '--'}</span></span>
                <span><span class="crypto-signal-detail-label">Risk</span> <span class="crypto-signal-detail-value">${sizing.risk_usd ? '$' + sizing.risk_usd.toFixed(0) + ' (' + sizing.risk_pct + '%)' : '--'}</span></span>
            </div>` : '';

    // Strategy-specific context row
    let contextHtml = '';
    const sLower = (signal.strategy || '').toLowerCase();
    if (sLower.includes('funding')) {
        const fr = enrichment.funding_rate;
        const mts = enrichment.minutes_to_settlement;
        if (fr !== undefined) {
            contextHtml = `<div class="crypto-signal-context"><span>Funding: <strong>${(fr * 100).toFixed(4)}%</strong></span>${mts !== undefined ? `<span>Settlement in: <strong>${mts}m</strong></span>` : ''}</div>`;
        }
    } else if (sLower.includes('session') || sLower.includes('sweep')) {
        const session = enrichment.current_session || enrichment.session;
        const sweepDir = enrichment.sweep_direction;
        if (session) {
            contextHtml = `<div class="crypto-signal-context"><span>Session: <strong>${session}</strong></span>${sweepDir ? `<span>Sweep: <strong>${sweepDir}</strong></span>` : ''}</div>`;
        }
    } else if (sLower.includes('liquidation') || sLower.includes('flush')) {
        const sellVol = enrichment.sell_volume_usd || enrichment.liquidation_volume;
        if (sellVol) {
            contextHtml = `<div class="crypto-signal-context"><span>Sell Volume: <strong>$${(sellVol / 1e6).toFixed(1)}M</strong></span>${enrichment.price_change_pct !== undefined ? `<span>Move: <strong>${enrichment.price_change_pct}%</strong></span>` : ''}</div>`;
        }
    } else if (sLower.includes('holy_grail')) {
        const adx = signal.adx || enrichment.adx;
        const rsi = signal.rsi || enrichment.rsi;
        if (adx || rsi) {
            contextHtml = `<div class="crypto-signal-context">${adx ? `<span>ADX: <strong>${adx}</strong></span>` : ''}${rsi ? `<span>RSI: <strong>${rsi}</strong></span>` : ''}</div>`;
        }
    }

    // Regime label
    const regime = enrichment.regime;
    const regimeHtml = regime ? `<span class="crypto-badge">${regime}</span>` : '';

    return `
        <div class="crypto-signal-card ${signalTypeClass}" data-signal-id="${signal.signal_id || ''}" data-signal="${encodeURIComponent(JSON.stringify(signal))}">
            <div class="crypto-signal-header">
                <span class="crypto-signal-ticker" data-action="view-chart">${escapeHtml(signal.ticker || '--')}</span>
                <div class="crypto-signal-meta">
                    ${badges.join('')}
                    ${regimeHtml}
                    <span class="crypto-badge">${escapeHtml(direction)}</span>
                </div>
            </div>
            <div class="crypto-signal-score">
                <span class="crypto-score-value">${scoreStr}</span>
                <span class="crypto-score-tier ${scoreTier.toLowerCase()}">${scoreTier}</span>
                ${msBadgeHtml}
                <span style="margin-left:auto;font-size:11px;color:var(--text-secondary)">${escapeHtml(strategy)}</span>
            </div>
            <div class="crypto-signal-details">
                <span><span class="crypto-signal-detail-label">Entry</span> <span class="crypto-signal-detail-value">${formatPrice(signal.entry_price)}</span></span>
                <span><span class="crypto-signal-detail-label">Stop</span> <span class="crypto-signal-detail-value">${formatPrice(signal.stop_loss)}</span></span>
                <span><span class="crypto-signal-detail-label">Target</span> <span class="crypto-signal-detail-value">${formatPrice(signal.target_1)}</span></span>
                <span><span class="crypto-signal-detail-label">R:R</span> <span class="crypto-signal-detail-value">${formatRiskReward(signal.risk_reward)}</span></span>
            </div>${msDetailHtml}${sizingHtml}${contextHtml}
            <div class="crypto-signal-bias ${biasClass}">${biasIcon} ${biasText}${ageLabel ? `  &middot;  <span class="signal-age ${ageClass}">${ageLabel}</span>` : ''}${timestampStr ? `  &middot;  ${timestampStr}` : ''}</div>
            <div class="crypto-signal-actions">
                <button class="action-btn dismiss-btn" data-action="dismiss">&#10005; Dismiss</button>
                <button class="action-btn select-btn" data-action="select">&#10003; Accept</button>
            </div>
        </div>
    `;
}

function createSignalCard(signal) {
    const typeLabel = formatSignalType(signal.signal_type || signal.strategy);
    
    // Calculate score tier and pulse class
    const score = signal.score || 0;
    const scoreTier = getScoreTier(score);
    const isStrongSignal = score >= 75;
    const pulseClass = isStrongSignal ? 'signal-pulse' : '';
    
    // Check bias alignment from signal data or calculate
    const biasAlignment = signal.bias_alignment || 'NEUTRAL';
    const isAligned = biasAlignment.includes('ALIGNED') && !biasAlignment.includes('COUNTER');
    const biasAlignmentClass = isAligned ? 'bias-aligned' : (biasAlignment === 'NEUTRAL' ? '' : 'bias-misaligned');
    const biasAlignmentIcon = isAligned ? 'OK' : (biasAlignment.includes('COUNTER') ? '!' : 'o');
    const biasAlignmentText = biasAlignment.replace('_', ' ');
    
    // Safe number formatting
    const formatPrice = (val) => val ? parseFloat(val).toFixed(2) : '-';
    const formatRR = (val) => formatRiskReward(val);

    // Committee data rendering
    const committeeData = signal.committee_data ?
        (typeof signal.committee_data === 'string' ? JSON.parse(signal.committee_data) : signal.committee_data)
        : null;
    const hasCommittee = !!(committeeData && committeeData.action);
    
    // Handle multiple strategies (deduplicated signals)
    let strategiesHtml = '';
    if (signal.strategies && signal.strategies.length > 1) {
        // Multiple strategies - show all
        strategiesHtml = signal.strategies.map(s => wrapWithKbLink(formatStrategyName(s))).join(' + ');
    } else {
        // Single strategy
        strategiesHtml = wrapWithKbLink(formatStrategyName(signal.strategy));
    }
    
    const typeWithKb = wrapWithKbLink(typeLabel);
    
    // Format timestamp as "Jan 28, 1:45 PM" (convert from UTC)
    let timestampStr = '';
    if (signal.timestamp || signal.created_at) {
        try {
            // Server stores UTC without 'Z', so add it for proper parsing
            let timeStr = signal.timestamp || signal.created_at;
            if (!timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
                timeStr += 'Z';  // Treat as UTC
            }
            const signalDate = new Date(timeStr);
            const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true };
            timestampStr = signalDate.toLocaleString('en-US', options);
        } catch (e) {
            timestampStr = '';
        }
    }
    
    const isCounterTrend = signal.is_counter_trend || signal.contrarian_qualified;
    const counterTrendClass = isCounterTrend ? 'counter-trend' : '';
    const counterTrendTag = isCounterTrend ? '<span class="counter-trend-tag">COUNTER-TREND</span>' : '';
    const contrarianTag = signal.contrarian_qualified ? '<span class="counter-trend-tag" style="color:#14b8a6;background:rgba(20,184,166,0.12)">CONTRARIAN</span>' : '';
    
    return `
        <div class="signal-card ${signal.signal_type || ''} ${biasAlignmentClass} ${pulseClass} ${counterTrendClass}" 
             data-signal-id="${signal.signal_id}" 
             data-signal="${encodeURIComponent(JSON.stringify(signal))}">
            
            <div class="signal-header">
                <div>
                    <div class="signal-type ${signal.signal_type || ''}">${typeWithKb}${counterTrendTag}${contrarianTag}</div>
                    <div class="signal-strategy">${strategiesHtml}</div>
                </div>
                <div class="signal-ticker ticker-link" data-action="view-chart">${signal.ticker}</div>
            </div>
            
            ${timestampStr ? `<div class="signal-timestamp">${timestampStr}</div>` : ''}
            
            <div class="signal-score-bar">
                <div class="score-label">Score</div>
                <div class="score-value ${scoreTier.toLowerCase()}">${score}</div>
                <div class="score-tier ${scoreTier.toLowerCase()}">${scoreTier}</div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">Entry</div>
                    <div class="signal-detail-value">${formatPrice(signal.entry_price)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Stop</div>
                    <div class="signal-detail-value">${formatPrice(signal.stop_loss)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Target</div>
                    <div class="signal-detail-value">${formatPrice(signal.target_1)}</div>
                </div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">R:R</div>
                    <div class="signal-detail-value">${formatRR(signal.risk_reward)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Direction</div>
                    <div class="signal-detail-value direction-${(signal.direction || '').toLowerCase()}">${signal.direction || '-'}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Confidence</div>
                    <div class="signal-detail-value">${signal.confidence || '-'}</div>
                </div>
            </div>
            
            <div class="signal-bias-indicator ${biasAlignmentClass}" title="${biasAlignmentText}">
                <span class="bias-icon">${biasAlignmentIcon}</span>
                <span class="bias-text">${biasAlignmentText}</span>
            </div>
            
            <div class="signal-actions">
                <button class="action-btn dismiss-btn" data-action="dismiss">Reject</button>
                ${hasCommittee ? (() => {
                    const action = committeeData.action;
                    const conviction = committeeData.conviction || '';
                    const badgeClass = action === 'TAKE' ? 'committee-take' : (action === 'PASS' ? 'committee-pass' : 'committee-watch');
                    return `<div class="committee-badge ${badgeClass}" data-action="toggle-committee">${action} &middot; ${conviction}</div>`;
                })() : `<button class="action-btn committee-btn" data-action="committee">Analyze</button>`}
                <button class="action-btn select-btn" data-action="select">Accept</button>
            </div>
            ${hasCommittee ? (() => {
                const r = committeeData.risk || {};
                const pivotText = committeeData.pivot ? committeeData.pivot.substring(0, 200) + (committeeData.pivot.length > 200 ? '...' : '') : '';
                return `
                <div class="committee-panel" style="display:none;">
                    <div class="committee-panel-header">Trading Team Analysis</div>
                    ${pivotText ? `<div class="committee-synthesis">${pivotText}</div>` : ''}
                    ${r.entry ? `<div class="committee-risk-row">Entry: <strong>${r.entry}</strong> | Stop: <strong>${r.stop || '--'}</strong> | Size: <strong>${r.size || '--'}</strong></div>` : ''}
                </div>`;
            })() : ''}
        </div>
    `;
}

function getBiasAlignmentStatus(cyclicalLevel, weeklyLevel) {
    const cyclicalBullish = isBullishBias(cyclicalLevel);
    const cyclicalBearish = isBearishBias(cyclicalLevel);
    const weeklyBullish = isBullishBias(weeklyLevel);
    const weeklyBearish = isBearishBias(weeklyLevel);

    if (cyclicalBullish && weeklyBullish) {
        return {
            note: 'Macro alignment: Bullish (Cyclical + Weekly aligned)',
            alignmentText: 'BULLISH ALIGNED',
            alignmentClass: 'bias-aligned-bullish'
        };
    }
    if (cyclicalBearish && weeklyBearish) {
        return {
            note: 'Macro alignment: Bearish (Cyclical + Weekly aligned)',
            alignmentText: 'BEARISH ALIGNED',
            alignmentClass: 'bias-aligned-bearish'
        };
    }
    return {
        note: 'Macro alignment: Mixed signals across timeframes',
        alignmentText: 'MIXED',
        alignmentClass: ''
    };
}

function renderCryptoBiasSummary() {
    const biasValues = {
        daily: _dailyBiasPrimaryData?.level || dailyBiasFullData?.level || 'NEUTRAL',
        composite: _compositeBiasData?.bias_level || 'NEUTRAL'
    };

    const inlineDaily = document.getElementById('cryptoBiasDaily');
    const inlineComposite = document.getElementById('cryptoCompositeInline');

    if (inlineDaily) inlineDaily.textContent = (biasValues.daily || '--').replace(/_/g, ' ');
    if (inlineComposite) inlineComposite.textContent = (biasValues.composite || 'NEUTRAL').replace(/_/g, ' ');

    const applyBiasPill = (pill, level) => {
        if (!pill) return;
        const biasKey = (level || 'NEUTRAL').toUpperCase();
        pill.classList.remove('TORO_MAJOR', 'TORO_MINOR', 'URSA_MINOR', 'URSA_MAJOR', 'NEUTRAL');
        pill.classList.add(biasKey);
    };

    applyBiasPill(document.querySelector('.bias-pill[data-bias="daily"]'), biasValues.daily);
    applyBiasPill(document.querySelector('.bias-pill[data-bias="composite"]'), biasValues.composite);

    const levelEl = document.getElementById('cryptoCompositeBiasLevel');
    const scoreEl = document.getElementById('cryptoCompositeBiasScore');
    const confEl = document.getElementById('cryptoCompositeBiasConfidence');

    const compositeLevel = (biasValues.composite || 'NEUTRAL').replace(/_/g, ' ');
    const compositeScoreVal = typeof _compositeBiasData?.composite_score === 'number'
        ? _compositeBiasData.composite_score
        : parseFloat(_compositeBiasData?.composite_score || 0);
    const compositeConf = (_compositeBiasData?.confidence || 'LOW').toUpperCase();
    const colors = BIAS_COLORS[_compositeBiasData?.bias_level] || BIAS_COLORS.NEUTRAL;

    if (levelEl) {
        levelEl.textContent = compositeLevel;
        levelEl.style.color = colors?.text || '#9fb7ff';
    }
    if (scoreEl) scoreEl.textContent = Number.isFinite(compositeScoreVal) ? `(${compositeScoreVal.toFixed(2)})` : '(--)';
    if (confEl) {
        confEl.textContent = compositeConf;
        confEl.style.color = '#ffffff';
    }
}

function getCryptoSignalPriority(signal) {
    const strategy = (signal.strategy || '').toLowerCase();
    if (strategy.includes('sniper')) return 3;
    if (strategy.includes('scout')) return 2;
    if (strategy.includes('exhaustion')) return 1;
    return 0;
}

function applyCryptoBiasPreset() {
    const autoToggle = document.getElementById('cryptoAutoBiasToggle');
    if (!autoToggle || !autoToggle.checked) return;

    const longCb = document.getElementById('cryptoFilterLong');
    const shortCb = document.getElementById('cryptoFilterShort');
    if (!longCb || !shortCb) return;

    const bias = (_compositeBiasData?.bias_level || 'NEUTRAL').toUpperCase();
    if (bias.includes('TORO')) {
        longCb.checked = true;
        shortCb.checked = false;
    } else if (bias.includes('URSA')) {
        longCb.checked = false;
        shortCb.checked = true;
    } else {
        longCb.checked = true;
        shortCb.checked = true;
    }
}

function renderCryptoPositions() {
    const container = document.getElementById('cryptoPositionsList');
    const countEl = document.getElementById('cryptoPositionsCount');
    if (!container) return;

    // Filter open positions for crypto
    const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
    const cryptoPositions = openPositions.filter(p => {
        if (p.asset_class === 'CRYPTO') return true;
        const tickerBase = (p.ticker || '').toUpperCase().replace(/USD.*/, '');
        return cryptoTickers.includes(tickerBase);
    });

    if (countEl) countEl.textContent = cryptoPositions.length;

    if (cryptoPositions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open crypto positions</p>';
        return;
    }

    container.innerHTML = cryptoPositions.map(p => `
        <div class="crypto-position-card">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span class="crypto-position-ticker">${escapeHtml(p.ticker || '--')}</span>
                <span class="crypto-position-direction ${p.direction || ''}" style="font-size:11px;font-weight:700">${escapeHtml(p.direction || '--')}</span>
            </div>
            <div class="crypto-position-meta">
                Entry: $${p.entry_price ? parseFloat(p.entry_price).toLocaleString() : '--'}
                &middot; Qty: ${p.quantity || '--'}
                ${p.stop_loss ? `&middot; Stop: $${parseFloat(p.stop_loss).toLocaleString()}` : ''}
                ${p.strategy ? `&middot; ${escapeHtml(formatStrategyName(p.strategy))}` : ''}
            </div>
        </div>
    `).join('');
}

async function loadCryptoKeyLevels() {
    const updatedEl = document.getElementById('cryptoKeyLevelsUpdated');
    // Note: was previously guarded by a 'cryptoKeyLevelsGrid' ID that no longer exists.
    // updateCryptoLevelValue() uses querySelectorAll('[data-level=...]') which targets
    // the strip elements directly, so no container reference needed here.

    try {
        const symbol = (cryptoCurrentSymbol || 'BTCUSD').replace(/USD$/, 'USDT');
        const daily = await fetchBinanceKlines(symbol, '1d', { limit: 3 });
        const weekly = await fetchBinanceKlines(symbol, '1w', { limit: 2 });
        const monthly = await fetchBinanceKlines(symbol, '1M', { limit: 2 });

        const today = daily?.[daily.length - 1];
        const yesterday = daily?.[daily.length - 2];

        const todayOpen = today ? parseFloat(today[1]) : null;
        const yesterdayClose = yesterday ? parseFloat(yesterday[4]) : null;

        const overnight = await fetchOvernightRange(symbol);
        const weeklyOpen = weekly?.[weekly.length - 1] ? parseFloat(weekly[weekly.length - 1][1]) : null;
        const monthlyOpen = monthly?.[monthly.length - 1] ? parseFloat(monthly[monthly.length - 1][1]) : null;

        updateCryptoLevelValue('todayOpen', todayOpen);
        updateCryptoLevelValue('yesterdayClose', yesterdayClose);
        updateCryptoLevelValue('overnightHigh', overnight?.high);
        updateCryptoLevelValue('overnightLow', overnight?.low);
        updateCryptoLevelValue('weeklyOpen', weeklyOpen);
        updateCryptoLevelValue('monthlyOpen', monthlyOpen);

        if (updatedEl) {
            updatedEl.textContent = `Updated ${new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
        }
    } catch (error) {
        console.error('Error loading crypto key levels:', error);
        if (updatedEl) {
            updatedEl.textContent = 'Update failed';
        }
    }
}

async function loadCryptoMarketData() {
    const spotEl = document.getElementById('cryptoCoinbaseSpotInline');
    if (!spotEl) return;

    let data = null;
    try {
        const symbol = (cryptoCurrentSymbol || 'BTCUSD').replace(/USD$/, 'USDT');
        const response = await fetch(`${API_URL}/crypto/market?symbol=${symbol}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        data = await response.json();
    } catch (error) {
        console.error('Error loading crypto market data:', error);
        // Keep the last good snapshot visible on transient API failures.
        if (cryptoMarketData) {
            renderCryptoMarketData();
        } else {
            renderCryptoMarketError();
        }
        return;
    }

    cryptoMarketData = data;

    try {
        renderCryptoMarketData();
    } catch (error) {
        // Keep last good values on screen if a render-only issue occurs.
        console.error('Error rendering crypto market data:', error);
    }
}

function renderCryptoMarketError() {
    const ids = [
        'cryptoCoinbaseSpotInline', 'cryptoBinanceSpotInline', 'cryptoBinancePerpInline',
        'cryptoPerpSourceInline', 'cryptoFundingInline', 'cryptoCvdInline', 'cryptoTakerBuy', 'cryptoTakerSell', 'cryptoCvdTrend'
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = '--';
            el.classList.remove('bullish', 'bearish');
        }
    });
}

function renderCryptoMarketData() {
    if (!cryptoMarketData) return;
    const prices = cryptoMarketData.prices || {};
    const funding = cryptoMarketData.funding || {};
    const cvd = cryptoMarketData.cvd || {};

    const rememberNumber = (key, value) => {
        const num = Number(value);
        if (value !== null && value !== undefined && !Number.isNaN(num)) {
            cryptoMarketLastGood[key] = num;
            return num;
        }
        return cryptoMarketLastGood[key] ?? null;
    };

    const rememberString = (key, value) => {
        if (value !== null && value !== undefined && `${value}`.trim() !== '') {
            cryptoMarketLastGood[key] = value;
            return value;
        }
        return cryptoMarketLastGood[key] ?? null;
    };

    const perps = prices.perps || {};
    const spotRaw = prices.coinbase_spot ?? prices.coinbase ?? prices.spot_coinbase ?? null;
    const binanceSpotRaw = prices.binance_spot ?? prices.binance ?? prices.spot_binance ?? prices.spot ?? null;
    const perpRaw = perps.binance ?? perps.bybit ?? perps.okx ?? perps.binance_perp ?? perps.perp ?? prices.perp_price ?? prices.perp ?? null;

    rememberNumber('coinbase_spot', spotRaw ?? binanceSpotRaw);
    rememberNumber('binance_spot', binanceSpotRaw);
    rememberNumber('perp_price', perpRaw);
    rememberString('binance_spot_ts', prices.binance_spot_ts);
    rememberString('perp_source', perps.source);

    const fundingInlineEl = document.getElementById('cryptoFundingInline');
    const cvdInlineEl = document.getElementById('cryptoCvdInline');

    if (fundingInlineEl) {
        const primaryFunding = rememberNumber(
            'funding_primary',
            funding.primary?.rate ?? funding.binance?.rate ?? funding.okx?.rate ?? funding.bybit?.rate ?? funding.okx_rate
        );
        const fundingSource = rememberString('funding_source', funding.primary?.source);
        const fundingSourceLabel = fundingSource ? `${String(fundingSource).toUpperCase()}` : '';
        const fundingLabel = fundingSourceLabel ? `Funding (${fundingSourceLabel})` : 'Funding';
        fundingInlineEl.textContent = formatFundingRate(primaryFunding, fundingLabel);
        // Color by numeric sign for immediate readability.
        fundingInlineEl.className = `crypto-price-extra ${primaryFunding > 0 ? 'bullish' : primaryFunding < 0 ? 'bearish' : ''}`.trim();
    }

    if (cvdInlineEl) {
        const netUsd = rememberNumber('cvd_net_usd', cvd.net_usd ?? cvd.net ?? cvd.value_usd);
        const cvdDir = rememberString('cvd_direction', cvd.direction ?? cvd.smoothed_direction ?? 'NEUTRAL');
        const cvdConfidence = rememberString('cvd_confidence', cvd.direction_confidence ?? '');
        if (netUsd !== null) {
            const confidenceBadge = (cvdDir && cvdDir !== 'NEUTRAL' && cvdConfidence) ? ` ${cvdConfidence.charAt(0)}` : '';
            const directionLabel = cvdDir && cvdDir !== 'NEUTRAL' ? `${cvdDir}${confidenceBadge}` : 'NEUTRAL';
            const compactValue = formatCompactSignedUsd(netUsd);
            cvdInlineEl.innerHTML = `<span class="crypto-cvd-direction">CVD ${directionLabel}</span> <span class="crypto-cvd-net">(${compactValue})</span>`;
        } else {
            cvdInlineEl.textContent = 'CVD --';
        }
        cvdInlineEl.className = `crypto-price-extra ${cvdDir?.includes('BULL') ? 'bullish' : cvdDir?.includes('BEAR') ? 'bearish' : ''}`.trim();
    }

    renderOrderflow(cvd, cryptoMarketData.order_flow || []);
    updateCryptoPriceStrip();
}

function updateCryptoPriceStrip() {
    const coinbaseEl = document.getElementById('cryptoCoinbaseSpotInline');
    const binanceSpotEl = document.getElementById('cryptoBinanceSpotInline');
    const binancePerpEl = document.getElementById('cryptoBinancePerpInline');
    const perpSourceEl = document.getElementById('cryptoPerpSourceInline');

    if (!coinbaseEl && !binanceSpotEl && !binancePerpEl) return;

    const prices = cryptoMarketData?.prices || {};
    const perps = prices.perps || {};
    const coinbaseSpot = cryptoMarketLastGood.coinbase_spot ?? prices.coinbase_spot ?? null;
    const binanceSpot = cryptoMarketLastGood.binance_spot ?? prices.binance_spot ?? null;
    const perpPrice = cryptoMarketLastGood.perp_price ?? perps.binance ?? perps.bybit ?? perps.okx ?? prices.perp_price ?? null;
    const perpSource = (cryptoMarketLastGood.perp_source ?? perps.source ?? '').toString().toUpperCase();
    const perpSourceMap = {
        BINANCE: 'BINANCE PERPS',
        BYBIT: 'BYBIT PERPS',
        OKX: 'OKX PERPS',
    };

    if (coinbaseEl) coinbaseEl.textContent = coinbaseSpot !== null ? formatUsdValue(coinbaseSpot) : '--';
    if (binanceSpotEl) binanceSpotEl.textContent = binanceSpot !== null ? formatUsdValue(binanceSpot) : '--';
    if (binancePerpEl) binancePerpEl.textContent = perpPrice !== null ? formatUsdValue(perpPrice) : '--';
    if (perpSourceEl) perpSourceEl.textContent = perpSourceMap[perpSource] || (perpSource ? `${perpSource} PERPS` : '--');

    const compareSpot = coinbaseSpot ?? binanceSpot ?? perpPrice;
    const wma = cryptoWma9;
    const trendClass = (wma !== null && compareSpot !== null && !Number.isNaN(Number(wma)) && !Number.isNaN(Number(compareSpot)))
        ? (Number(compareSpot) >= Number(wma) ? 'bullish' : 'bearish')
        : null;

    [coinbaseEl, binanceSpotEl, binancePerpEl].forEach(el => {
        if (!el) return;
        el.classList.remove('bullish', 'bearish');
        if (trendClass) el.classList.add(trendClass);
    });
}

function renderOrderflow(cvd, tape) {
    const takerBuyEl = document.getElementById('cryptoTakerBuy');
    const takerSellEl = document.getElementById('cryptoTakerSell');
    const cvdTrendEl = document.getElementById('cryptoCvdTrend');
    const tapeEl = document.getElementById('cryptoOrderflowTape');
    const updatedEl = document.getElementById('cryptoOrderflowUpdated');
    const sparklineEl = document.getElementById('cryptoCvdSparkline');

    if (takerBuyEl) takerBuyEl.textContent = (cvd?.taker_buy_qty !== null && cvd?.taker_buy_qty !== undefined) ? `${Number(cvd.taker_buy_qty).toFixed(2)} BTC` : '--';
    if (takerSellEl) takerSellEl.textContent = (cvd?.taker_sell_qty !== null && cvd?.taker_sell_qty !== undefined) ? `${Number(cvd.taker_sell_qty).toFixed(2)} BTC` : '--';
    if (cvdTrendEl) {
        const dir = cvd?.direction || 'NEUTRAL';
        const confidence = (cvd?.direction_confidence || '').toUpperCase();
        cvdTrendEl.textContent = (confidence && dir !== 'NEUTRAL') ? `${dir} (${confidence})` : dir;
        cvdTrendEl.className = `metric-value ${dir.includes('BULL') ? 'bullish' : dir.includes('BEAR') ? 'bearish' : 'neutral'}`;
    }
    if (updatedEl) {
        const stamp = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
        const source = (cvd?.source || '').toString().toUpperCase();
        updatedEl.textContent = source ? `${source} ${stamp}` : stamp;
    }

    if (sparklineEl) {
        sparklineEl.innerHTML = renderSparklineSvg(cvd?.cvd_series || []);
    }

    if (tapeEl) {
        if (!tape || tape.length === 0) {
            tapeEl.innerHTML = '<p class="empty-state">No tape yet</p>';
        } else {
            tapeEl.innerHTML = tape.map(row => {
                const sideClass = row.side === 'BUY' ? 'buy' : 'sell';
                const price = row.price ? row.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--';
                const qty = row.qty ? row.qty.toFixed(3) : '--';
                return `<div class="orderflow-tape-row ${sideClass}"><span>${row.side}</span><span>$${price}</span><span>${qty} BTC</span></div>`;
            }).join('');
        }
    }
}

function renderSparklineSvg(series) {
    if (!series || series.length < 2) {
        return '<svg viewBox="0 0 100 50"><path d="M0 25 L100 25" stroke="#314255" stroke-width="2" fill="none" /></svg>';
    }
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = max - min || 1;
    const points = series.map((v, i) => {
        const x = (i / (series.length - 1)) * 100;
        const y = 50 - ((v - min) / range) * 45 - 2;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    return `<svg viewBox=\"0 0 100 50\" preserveAspectRatio=\"none\"><polyline points=\"${points}\" fill=\"none\" stroke=\"#00e5ff\" stroke-width=\"2\" /></svg>`;
}

function formatUsdValue(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedUsd(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}$${Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCompactSignedUsd(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const abs = Math.abs(num);
    const sign = num >= 0 ? '+' : '-';
    let compact = '';
    if (abs >= 1_000_000_000) {
        compact = `${(abs / 1_000_000_000).toFixed(2)}B`;
    } else if (abs >= 1_000_000) {
        compact = `${(abs / 1_000_000).toFixed(2)}M`;
    } else if (abs >= 1_000) {
        compact = `${(abs / 1_000).toFixed(1)}K`;
    } else {
        compact = abs.toFixed(0);
    }
    return `${sign}$${compact}`;
}

function formatSignedPercent(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
}

function formatFundingRate(rate, label) {
    if (rate === null || rate === undefined || Number.isNaN(rate)) return `${label}: --`;
    const num = Number(rate);
    const pct = num * 100;
    const sign = pct >= 0 ? '+' : '';
    const side = num > 0 ? 'Longs pay' : num < 0 ? 'Shorts pay' : 'Flat';
    return `${label}: ${sign}${pct.toFixed(4)}% (${side})`;
}

function updateCryptoLevelValue(levelKey, value) {
    const formatted = (value !== null && value !== undefined && !Number.isNaN(value))
        ? `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
        : '--';
    // Update all matching elements (strip <b> tags + any other data-level targets)
    document.querySelectorAll(`[data-level="${levelKey}"]`).forEach(el => {
        const b = el.querySelector('b');
        if (b) {
            b.textContent = formatted;
        } else {
            el.textContent = formatted;
        }
    });
}

async function fetchBinanceKlines(symbol, interval, params = {}) {
    const url = new URL(`${API_URL}/crypto/binance/klines`);
    url.searchParams.set('symbol', symbol);
    url.searchParams.set('interval', interval);
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            url.searchParams.set(key, value);
        }
    });

    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`Binance proxy error: ${response.status}`);
    }
    const result = await response.json();
    if (result.status !== 'success') {
        throw new Error(result.error || 'Binance proxy error');
    }
    return result.data;
}

function calculateWeightedMovingAverage(values) {
    if (!Array.isArray(values) || values.length === 0) return null;
    let weightedSum = 0;
    let weightTotal = 0;
    values.forEach((value, idx) => {
        const weight = idx + 1;
        weightedSum += Number(value) * weight;
        weightTotal += weight;
    });
    if (weightTotal === 0) return null;
    return weightedSum / weightTotal;
}

function extractSessionOpenPrices(klines) {
    if (!Array.isArray(klines)) return [];
    return klines
        .filter(row => {
            const openTime = row?.[0];
            if (!openTime) return false;
            const date = new Date(openTime);
            return date.getUTCHours() === 1; // 8:00pm EST = 01:00 UTC
        })
        .map(row => Number(row?.[1]))
        .filter(value => !Number.isNaN(value));
}

async function refreshCryptoWma9() {
    if (cryptoWmaLoading) return;
    cryptoWmaLoading = true;
    try {
        const klines = await fetchBinanceKlines('BTCUSDT', '1h', { limit: 240 });
        const sessionOpens = extractSessionOpenPrices(klines);
        if (sessionOpens.length >= 9) {
            const lastNine = sessionOpens.slice(-9);
            const wma = calculateWeightedMovingAverage(lastNine);
            if (wma !== null && !Number.isNaN(wma)) {
                cryptoWma9 = wma;
                cryptoWmaUpdated = Date.now();
            }
        }
    } catch (error) {
        console.error('Error refreshing BTC 9-day WMA:', error);
    } finally {
        cryptoWmaLoading = false;
        updateCryptoPriceStrip();
    }
}

async function fetchOvernightRange(symbol) {
    const now = new Date();
    const start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0);
    const end = start + 8 * 60 * 60 * 1000;

    const klines = await fetchBinanceKlines(symbol, '1h', {
        startTime: start,
        endTime: end
    });

    if (!Array.isArray(klines) || klines.length === 0) {
        return null;
    }

    const highs = klines.map(k => parseFloat(k[2]));
    const lows = klines.map(k => parseFloat(k[3]));

    return {
        high: Math.max(...highs),
        low: Math.min(...lows)
    };
}

function getScoreTier(score) {
    if (score >= 85) return 'EXCEPTIONAL';
    if (score >= 75) return 'STRONG';
    if (score >= 60) return 'MODERATE';
    if (score >= 45) return 'WEAK';
    return 'LOW';
}

function attachSignalActions() {
    // Clickable ticker to view on chart
    document.querySelectorAll('.ticker-link').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = e.target.closest('.signal-card');
            const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
            showTradeOnChart(signal);
        });
    });
    
    // Dismiss and Select buttons
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', handleSignalAction);
    });
}

function attachReloadPreviousHandler() {
    const btn = document.querySelector('.reload-previous-btn');
    if (!btn) return;
    btn.addEventListener('click', loadMoreTradeIdeas);
}

async function loadMoreTradeIdeas() {
    const pagination = tradeIdeasPagination.equity;
    if (!pagination || pagination.loading || !pagination.hasMore) return;

    pagination.loading = true;
    refreshSignalViews();

    try {
        const response = await fetch(
            `${API_URL}/signals/active/paged?limit=${pagination.limit}&offset=${pagination.offset}`
        );
        const data = await response.json();

        if (data.status === 'success' && Array.isArray(data.signals)) {
            const allExisting = new Set([...signals.equity, ...signals.crypto].map(s => s.signal_id));
            const newSignals = data.signals.filter(s => !allExisting.has(s.signal_id));
            // Route into correct bucket
            newSignals.forEach(s => {
                if (s.asset_class === 'CRYPTO') signals.crypto.push(s);
                else signals.equity.push(s);
            });
            pagination.offset = signals.equity.length + signals.crypto.length;
            pagination.hasMore = data.has_more ?? (newSignals.length >= pagination.limit);
        } else {
            pagination.hasMore = false;
        }
    } catch (error) {
        console.error('Error loading previous trade ideas:', error);
    } finally {
        pagination.loading = false;
        refreshSignalViews();
    }
}

async function handleSignalAction(event) {
    event.stopPropagation();
    const button = event.target;
    const card = button.closest('.signal-card');
    const signalId = card.dataset.signalId;
    const action = button.dataset.action.toUpperCase();
    
    if (action === 'VIEW-CHART') return; // Handled separately
    
    if (action === 'SELECT') {
        // Open position entry modal instead of directly selecting
        const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
        openPositionEntryModal(signal, card);
        return;
    }
    
    if (action === 'DISMISS') {
        // Open dismiss modal with reason selection
        const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
        openDismissModal(signal, card);
        return;
    }

    if (action === 'COMMITTEE') {
        const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
        await requestCommitteeReview(signal, card);
        return;
    }

    if (action === 'TOGGLE-COMMITTEE') {
        const panel = card.querySelector('.committee-panel');
        if (panel) {
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }
        return;
    }
}

async function requestCommitteeReview(signal, card) {
    const btn = card.querySelector('.committee-btn');
    try {
        if (btn) {
            btn.textContent = 'Pending';
            btn.disabled = true;
            btn.classList.add('committee-pending');
        }
        const response = await fetch(`${API_URL}/trade-ideas/${signal.signal_id}/status`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({ status: 'COMMITTEE_REVIEW', decision_source: 'dashboard' })
        });
        const data = await response.json();
        if (data.new_status === 'COMMITTEE_REVIEW') {
            if (btn) btn.textContent = 'Sent';
        } else {
            if (btn) { btn.textContent = 'Failed'; btn.classList.remove('committee-pending'); }
        }
    } catch (err) {
        console.error('Committee request failed:', err);
        if (btn) { btn.textContent = 'Failed'; btn.disabled = false; btn.classList.remove('committee-pending'); }
    }
}

async function dismissSignalWithReason(signalId, reason, notes, card) {
    try {
        const response = await fetch(`${API_URL}/signals/${signalId}/dismiss`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                signal_id: signalId,
                reason: reason,
                notes: notes
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'dismissed') {
            // Remove card with animation
            card.style.opacity = '0';
            card.style.transform = 'translateX(-20px)';
            setTimeout(() => {
                card.remove();
                // Auto-refill Trade Ideas list
                refillTradeIdeas();
            }, 300);
        }
    } catch (error) {
        console.error('Error dismissing signal:', error);
    }
}

function openDismissModal(signal, card) {
    // Check for committee override context
    let committeeData = signal.committee_data;
    if (typeof committeeData === 'string') {
        try { committeeData = JSON.parse(committeeData); } catch(e) { committeeData = null; }
    }
    const isCommitteeOverride = committeeData && committeeData.action === 'TAKE';

    const committeeWarningHtml = isCommitteeOverride ? `
        <div class="committee-override-warning">
            Trading Team said <strong class="committee-take">TAKE</strong>
            (${committeeData.conviction || ''}) &mdash; dismissing this is an override.
        </div>
        <div class="modal-field">
            <label>Override Reason (helps the team learn)</label>
            <input type="text" id="dismissOverrideReason" placeholder="e.g. Too wide spread, better setup available...">
        </div>
    ` : '';

    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal dismiss-modal">
            <div class="modal-header">
                <h3>Dismiss ${signal.ticker} Signal</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                ${committeeWarningHtml}
                <p>Why are you dismissing this signal?</p>
                <div class="dismiss-reasons">
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="NOT_ALIGNED">
                        <span>Not aligned with my thesis</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="MISSED_ENTRY">
                        <span>Missed optimal entry</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="TECHNICAL_CONCERN">
                        <span>Technical concerns</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="OTHER" checked>
                        <span>Other / No reason</span>
                    </label>
                </div>
                <div class="modal-field">
                    <label>Notes (optional)</label>
                    <textarea id="dismissNotes" placeholder="Additional notes..."></textarea>
                </div>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn dismiss">Dismiss Signal</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Handle close
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());

    // Handle dismiss
    modal.querySelector('.modal-btn.dismiss').addEventListener('click', async () => {
        const reason = modal.querySelector('input[name="dismissReason"]:checked')?.value || 'OTHER';
        const notes = modal.querySelector('#dismissNotes').value;
        const overrideReason = modal.querySelector('#dismissOverrideReason')?.value || '';
        const combinedNotes = overrideReason ? `${overrideReason} | ${notes}` : notes;

        modal.remove();
        await dismissSignalWithReason(signal.signal_id, reason, combinedNotes, card);
    });

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function refillTradeIdeas() {
    // Fetch updated signal queue and re-render
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        if (data.status === 'success' && data.signals) {
            // Update in-memory signals
            signals.equity = data.signals.filter(s => s.asset_class === 'EQUITY' || !s.asset_class);
            signals.crypto = data.signals.filter(s => s.asset_class === 'CRYPTO');
            resetTradeIdeasPagination();
            
            // Re-render
            refreshSignalViews();
            
            console.log(`Trade Ideas refilled: ${data.signals.length} signals`);
        }
    } catch (error) {
        console.error('Error refilling trade ideas:', error);
    }
}

// Signal Management
function addSignal(signalData) {
    if (signalData.asset_class === 'EQUITY') {
        signals.equity.unshift(signalData);
    } else {
        signals.crypto.unshift(signalData);
    }
    syncTradeIdeasOffset(signalData.asset_class === 'EQUITY' ? 'equity' : 'crypto');
    refreshSignalViews();
}

function removeSignal(signalId) {
    signals.equity = signals.equity.filter(s => s.signal_id !== signalId);
    signals.crypto = signals.crypto.filter(s => s.signal_id !== signalId);
    syncTradeIdeasOffset('equity');
    syncTradeIdeasOffset('crypto');
    refreshSignalViews();
}

// Bias Updates
function updateBias(biasData) {
    const timeframe = biasData.timeframe.toLowerCase();
    const container = document.getElementById(`${timeframe}Bias`);
    const levelElement = document.getElementById(`${timeframe}Level`);
    const detailsElement = document.getElementById(`${timeframe}Details`);
    
    if (levelElement) {
        levelElement.textContent = biasData.level.replace('_', ' ');
        levelElement.className = `bias-level ${biasData.level}`;
    }
    
    if (container) {
        container.classList.remove('bullish', 'bearish', 'neutral');
        if (biasData.level.includes('TORO')) {
            container.classList.add('bullish');
        } else if (biasData.level.includes('URSA')) {
            container.classList.add('bearish');
        } else {
            container.classList.add('neutral');
        }
    }
    
    if (detailsElement && biasData.details) {
        detailsElement.innerHTML = biasData.details;
    }
}

function updatePosition(positionData) {
    loadOpenPositionsEnhanced();
}

// ==========================================
// HUNTER SCANNER
// ==========================================

let hunterResults = {
    ursa: [],
    taurus: []
};

// Initialize Hunter Scanner
function initHunterScanner() {
    const runScanBtn = document.getElementById('runScanBtn');
    if (runScanBtn) {
        runScanBtn.addEventListener('click', runHunterScan);
    }
    
    // Load any cached results
    loadHunterResults();
}

// Run a new scan
async function runHunterScan() {
    const btn = document.getElementById('runScanBtn');
    const status = document.getElementById('scanStatus');
    
    // Disable button and update status
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    status.textContent = 'Scanning S&P 500...';
    status.classList.add('scanning');
    
    try {
        // Trigger the scan
        const response = await fetch(`${API_URL}/scanner/run`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ mode: 'all' })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            // Poll for results
            pollForResults();
        } else {
            throw new Error(data.message || 'Scan failed to start');
        }
        
    } catch (error) {
        console.error('Hunter scan error:', error);
        status.textContent = 'Scan failed';
        status.classList.remove('scanning');
        btn.disabled = false;
        btn.textContent = 'Run Scan';
    }
}

// Poll for scan results
async function pollForResults() {
    const btn = document.getElementById('runScanBtn');
    const status = document.getElementById('scanStatus');
    
    let attempts = 0;
    const maxAttempts = 60; // 5 minutes max
    
    const poll = async () => {
        try {
            const response = await fetch(`${API_URL}/scanner/status`);
            const data = await response.json();
            
            if (data.status === 'complete') {
                // Scan complete, load results
                await loadHunterResults();
                status.textContent = 'Scan complete';
                status.classList.remove('scanning');
                btn.disabled = false;
                btn.textContent = 'Run Scan';
                return;
            }
            
            if (data.status === 'scanning' && attempts < maxAttempts) {
                attempts++;
                status.textContent = `Scanning... (${attempts * 5}s)`;
                setTimeout(poll, 5000); // Poll every 5 seconds
            } else if (data.status && data.status.startsWith('error')) {
                throw new Error(data.status);
            }
            
        } catch (error) {
            console.error('Poll error:', error);
            status.textContent = 'Error';
            status.classList.remove('scanning');
            btn.disabled = false;
            btn.textContent = 'Run Scan';
        }
    };
    
    poll();
}

// Load Hunter results from API
async function loadHunterResults() {
    try {
        const response = await fetch(`${API_URL}/scanner/results`);
        const data = await response.json();
        
        if (data.status === 'success') {
            hunterResults.ursa = data.ursa_signals || [];
            hunterResults.taurus = data.taurus_signals || [];
            renderHunterResults();
        }
        
    } catch (error) {
        console.error('Error loading Hunter results:', error);
    }
}

// Render Hunter results
function renderHunterResults() {
    renderUrsaSignals();
    renderTaurusSignals();
}

function renderUrsaSignals() {
    const container = document.getElementById('ursaSignals');
    const countEl = document.getElementById('ursaCount');
    
    if (!container) return;
    
    countEl.textContent = hunterResults.ursa.length;
    
    if (hunterResults.ursa.length === 0) {
        container.innerHTML = '<p class="empty-state">No trapped longs detected</p>';
        return;
    }
    
    container.innerHTML = hunterResults.ursa.map(signal => createHunterCard(signal, 'ursa')).join('');
    attachHunterCardEvents();
}

function renderTaurusSignals() {
    const container = document.getElementById('taurusSignals');
    const countEl = document.getElementById('taurusCount');
    
    if (!container) return;
    
    countEl.textContent = hunterResults.taurus.length;
    
    if (hunterResults.taurus.length === 0) {
        container.innerHTML = '<p class="empty-state">No trapped shorts detected</p>';
        return;
    }
    
    container.innerHTML = hunterResults.taurus.map(signal => createHunterCard(signal, 'taurus')).join('');
    attachHunterCardEvents();
}

function createHunterCard(signal, type) {
    const priority = signal.action_required?.priority || 'MEDIUM';
    const metrics = signal.quality_metrics || {};
    const marketData = signal.market_data || {};
    const instruction = signal.action_required?.sniper_instruction || '';
    
    return `
        <div class="hunter-card" data-symbol="${signal.symbol}">
            <div class="hunter-card-header">
                <span class="hunter-ticker" data-symbol="${signal.symbol}">${signal.symbol}</span>
                <span class="hunter-priority ${priority.toLowerCase()}">${priority}</span>
            </div>
            <div class="hunter-metrics">
                <div class="hunter-metric">
                    <div class="hunter-metric-label">ADX</div>
                    <div class="hunter-metric-value">${metrics.adx_trend_strength?.toFixed(1) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">RSI</div>
                    <div class="hunter-metric-value">${metrics.rsi_momentum?.toFixed(1) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">RVOL</div>
                    <div class="hunter-metric-value">${metrics.rvol_institutional?.toFixed(1) || '-'}x</div>
                </div>
            </div>
            <div class="hunter-metrics">
                <div class="hunter-metric">
                    <div class="hunter-metric-label">Price</div>
                    <div class="hunter-metric-value">$${marketData.current_price?.toFixed(2) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">VWAP</div>
                    <div class="hunter-metric-value">$${marketData.vwap_20?.toFixed(2) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">From VWAP</div>
                    <div class="hunter-metric-value">${marketData.pct_distance_from_vwap?.toFixed(1) || '-'}%</div>
                </div>
            </div>
            ${instruction ? `<div class="hunter-instruction">${instruction}</div>` : ''}
        </div>
    `;
}

function attachHunterCardEvents() {
    // Click ticker to view on chart
    document.querySelectorAll('.hunter-ticker').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            const symbol = e.target.dataset.symbol;
            changeChartSymbol(symbol);
        });
    });
    
    // Click card to view on chart
    document.querySelectorAll('.hunter-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (!e.target.classList.contains('hunter-ticker')) {
                const symbol = card.dataset.symbol;
                changeChartSymbol(symbol);
            }
        });
    });
}

// Add Hunter initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Hunter Scanner after a short delay
    setTimeout(initHunterScanner, 500);
    
    // Initialize Watchlist
    setTimeout(initWatchlist, 600);
    
    // Initialize Ticker Analyzer
    setTimeout(initTickerAnalyzer, 700);
});


// ==========================================
// WATCHLIST MANAGEMENT (v3)
// ==========================================

let watchlistRefreshInterval = null;
let watchlistLastData = null;
let watchlistTickerCache = [];
let watchlistCounts = {};
let selectedTickers = new Set();
let lastAnalyzedTicker = null;

const ZONE_COLORS = {
    MAX_LONG: { bg: '#0a2e1a', text: '#00e676' },
    LEVERAGED_LONG: { bg: '#0a2e2a', text: '#4caf50' },
    DE_LEVERAGING: { bg: '#2e2e0a', text: '#ffeb3b' },
    WATERFALL: { bg: '#2e1a0a', text: '#ff9800' },
    CAPITULATION: { bg: '#2e0a0a', text: '#e5370e' },
    RECOVERY: { bg: '#0a1a2e', text: '#42a5f5' },
    NEUTRAL: { bg: '#1a2228', text: '#78909c' }
};

function initWatchlist() {
    initWatchlistV3();
}

function initWatchlistV3() {
    const sectorSort = document.getElementById('watchlist-sector-sort');
    if (sectorSort) {
        sectorSort.addEventListener('change', () => {
            watchlistLastData = null;
            fetchEnrichedWatchlist();
        });
    }

    const refreshBtn = document.getElementById('watchlist-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            watchlistLastData = null;
            fetchEnrichedWatchlist();
        });
    }

    // RADAR pill click handlers
    document.querySelectorAll('.radar-filter-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.radar-filter-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            renderTickerList();
        });
    });
    document.querySelectorAll('.radar-sort-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.radar-sort-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            renderTickerList();
        });
    });

    const tickersRefresh = document.getElementById('tickers-refresh');
    if (tickersRefresh) {
        tickersRefresh.addEventListener('click', () => fetchTickerList(true));
    }

    setupBulkActions();
    fetchEnrichedWatchlist();
    fetchTickerList(true);
    startWatchlistRefresh();
}

async function fetchEnrichedWatchlist() {
    const grid = document.getElementById('watchlist-grid');
    if (!grid) return;

    const sortSelect = document.getElementById('watchlist-sector-sort');
    const sortBy = sortSelect ? sortSelect.value : 'strength_rank';

    try {
        const url = `${API_URL}/watchlist/enriched?sort_by=${encodeURIComponent(sortBy)}`;
        if (!watchlistLastData) {
            grid.innerHTML = '<div class="watchlist-loading">Loading watchlist data...</div>';
        }

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.status === 'success') {
            watchlistLastData = data;
            renderSectorWatchlist(data);
            renderBenchmark(data.benchmark);
            updateEnrichedTimestamp(data.enriched_at);
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Watchlist fetch failed:', error);
        grid.innerHTML = `
            <div class="watchlist-error">
                Failed to load watchlist data<br>
                <span style="font-size:11px;color:#78909c">${error.message}</span>
            </div>
        `;
    }
}

function renderBenchmark(benchmark) {
    const el = document.getElementById('watchlist-benchmark');
    if (!el) return;
    if (!benchmark) {
        el.innerHTML = '';
        return;
    }
    const price = benchmark.price !== null && benchmark.price !== undefined
        ? `$${Number(benchmark.price).toFixed(2)}`
        : '-';
    const chg = formatChange(benchmark.change_1d);
    const color = changeColor(benchmark.change_1d);
    el.innerHTML = `
        <span class="benchmark-label">${escapeHtml(benchmark.symbol || 'SPY')}</span>
        <span class="benchmark-price">${price}</span>
        <span style="color:${color}">${chg}</span>
    `;
}

function updateEnrichedTimestamp(ts) {
    const el = document.getElementById('watchlist-enriched-at');
    if (!el) return;
    const dt = ts ? new Date(ts) : new Date();
    el.textContent = `Updated: ${dt.toLocaleTimeString()}`;
}

function renderSectorWatchlist(data) {
    const grid = document.getElementById('watchlist-grid');
    if (!grid) return;

    const sectors = Array.isArray(data.sectors) ? data.sectors : [];
    if (!sectors.length) {
        grid.innerHTML = '<div class="watchlist-loading">No sectors available</div>';
        return;
    }

    grid.innerHTML = '';

    sectors.forEach(sector => {
        const card = document.createElement('div');
        card.className = 'sector-card';

        const vsSpy = sector.vs_spy_1w ?? sector.vs_spy_1d;
        const vsSpyLabel = formatChange(vsSpy);
        const vsSpyColor = changeColor(vsSpy);
        const etf = sector.etf || '-';
        const rank = sector.strength_rank !== undefined && sector.strength_rank !== null
            ? `#${sector.strength_rank}`
            : '#-';
        const bias = sector.bias_alignment || 'NEUTRAL';

        card.innerHTML = `
            <div class="sector-header">
                <div class="sector-title-row">
                    <span class="sector-name">${escapeHtml(sector.name || 'Uncategorized')}</span>
                    <span class="sector-etf">${escapeHtml(etf)}</span>
                    <span class="sector-vs-spy" style="color:${vsSpyColor}">${vsSpyLabel}</span>
                </div>
                <div class="sector-meta">
                    <span class="sector-bias">${escapeHtml(bias)}</span>
                    <span class="sector-rank">${escapeHtml(rank)}</span>
                </div>
            </div>
            <div class="ticker-header-row">
                <div>Symbol</div>
                <div class="col-price">Price</div>
                <div class="col-1d">1D</div>
                <div class="col-1w">1W</div>
                <div class="col-zone">CTA</div>
                <div class="col-signals">Sigs</div>
            </div>
        `;

        const tickers = sector.tickers || [];
        tickers.forEach(ticker => {
            const row = document.createElement('div');
            row.className = 'ticker-row';
            row.dataset.symbol = ticker.symbol;

            const price = ticker.price !== null && ticker.price !== undefined
                ? `$${Number(ticker.price).toFixed(2)}`
                : '-';
            const zone = ticker.cta_zone || 'NEUTRAL';
            const zoneStyle = ZONE_COLORS[zone] || ZONE_COLORS.NEUTRAL;
            const signals = ticker.active_signals || 0;

            row.innerHTML = `
                <div class="ticker-symbol">${escapeHtml(ticker.symbol)}</div>
                <div class="col-price">${price}</div>
                <div class="col-1d" style="color:${changeColor(ticker.change_1d)}">${formatChange(ticker.change_1d)}</div>
                <div class="col-1w" style="color:${changeColor(ticker.change_1w)}">${formatChange(ticker.change_1w)}</div>
                <div class="col-zone">
                    <span class="zone-badge" style="background:${zoneStyle.bg};color:${zoneStyle.text}">
                        ${escapeHtml(zone.replace(/_/g, ' '))}
                    </span>
                </div>
                <div class="col-signals ${signals > 0 ? 'signal-active' : 'signal-none'}">${signals || '-'}</div>
            `;

            row.addEventListener('click', () => openTickerChart(ticker.symbol));
            card.appendChild(row);
        });

        grid.appendChild(card);
    });
}

function startWatchlistRefresh() {
    stopWatchlistRefresh();
    watchlistRefreshInterval = setInterval(() => {
        fetchEnrichedWatchlist();
        fetchTickerList();
    }, 60000);
}

function stopWatchlistRefresh() {
    if (watchlistRefreshInterval) {
        clearInterval(watchlistRefreshInterval);
        watchlistRefreshInterval = null;
    }
}

async function fetchTickerList(force = false) {
    const list = document.getElementById('ticker-list');
    if (!list) return;

    const sortSelect = document.getElementById('ticker-sort');
    const sortBy = sortSelect ? sortSelect.value : 'sector';
    const sortDir = sortBy === 'sector' ? 'asc' : 'desc';

    if (force) {
        list.innerHTML = '<div class="watchlist-loading">Loading tickers...</div>';
    }

    try {
        const url = `${API_URL}/watchlist/tickers?sort_by=${encodeURIComponent(sortBy)}&sort_dir=${sortDir}&include_enrichment=true`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.status === 'success') {
            watchlistTickerCache = data.tickers || [];
            watchlistCounts = data.counts || {};
            renderTickerList();
            updateTickersTimestamp();
            updateTickerMeta();
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Ticker list fetch failed:', error);
        const message = error && error.message ? error.message : 'Unknown error';
        list.innerHTML = `
            <div class="watchlist-error">
                Failed to load tickers<br>
                <span style="font-size:11px;color:#78909c">${message}</span>
            </div>
        `;
    }
}

function getFilteredTickers() {
    const activePill = document.querySelector('.radar-filter-pill.active');
    const filterVal = activePill ? activePill.dataset.filter : 'all';
    const all = watchlistTickerCache || [];

    if (filterVal === 'mine') {
        return all.filter(t => t.on_watchlist || t.source === 'manual' || t.source === 'position');
    }
    if (filterVal === 'positions') {
        return all.filter(t =>
            openPositions.some(p => (p.ticker || '').toUpperCase() === (t.symbol || '').toUpperCase())
        );
    }
    if (filterVal === 'scanner') {
        return all.filter(t => t.scanner_universe || t.source === 'scanner');
    }
    if (filterVal === 'muted') {
        return all.filter(t => t.muted);
    }
    return all;
}

function updateTickerMeta() {
    const countEl = document.getElementById('ticker-count');
    const filtered = getFilteredTickers();
    if (countEl) {
        countEl.textContent = `${filtered.length} tickers`;
    }
}

function updateTickersTimestamp() {
    const el = document.getElementById('tickers-updated-at');
    if (!el) return;
    const now = new Date();
    el.textContent = `Updated: ${now.toLocaleTimeString()}`;
}

function renderTickerList() {
    const list = document.getElementById('ticker-list');
    if (!list) return;

    const activeSort = document.querySelector('.radar-sort-pill.active');
    const sortBy = activeSort ? activeSort.dataset.sort : 'change_1d';

    let filtered = getFilteredTickers();
    updateTickerMeta();

    filtered.sort((a, b) => {
        if (sortBy === 'change_1d') return (b.change_1d || 0) - (a.change_1d || 0);
        if (sortBy === 'relative_volume') return (b.relative_volume || 0) - (a.relative_volume || 0);
        if (sortBy === 'cta_zone') return (a.cta_zone || '').localeCompare(b.cta_zone || '');
        if (sortBy === 'sector') return (a.sector || '').localeCompare(b.sector || '');
        return 0;
    });

    if (filtered.length === 0) {
        list.innerHTML = '<p class="empty-state">No tickers match filter</p>';
        return;
    }
    list.innerHTML = '';
    list.className = 'ticker-list radar-grid';
    filtered.forEach(t => {
        const change = t.change_1d || 0;
        const changeColor = change > 0 ? '#4caf50' : change < 0 ? '#e5370e' : '#78909c';
        const changeSign = change >= 0 ? '+' : '';
        const rvol = t.relative_volume || 0;
        const rvolBar = Math.min(100, (rvol / 3) * 100);
        const matchingPos = openPositions.find(p =>
            (p.ticker || '').toUpperCase() === (t.symbol || '').toUpperCase()
        );
        let positionLabel = '';
        if (matchingPos) {
            const dir = (matchingPos.direction || '').toUpperCase();
            const structure = matchingPos.structure || matchingPos.asset_type || '';
            positionLabel = `<div class="radar-position-label ${dir.toLowerCase()}">${dir === 'BEARISH' || dir === 'SHORT' ? 'SHORT' : 'LONG'}: ${escapeHtml(structure)}</div>`;
        }
        const hasSignals = t.active_signals > 0;
        const signalDot = hasSignals ? '<span class="radar-signal-dot"></span>' : '';
        const zone = t.cta_zone || '';
        const zonePipColor = zone.includes('LONG') ? '#00e676'
                           : zone.includes('CAPIT') || zone.includes('WATER') ? '#e5370e'
                           : zone.includes('RECOV') ? '#42a5f5' : '#78909c';
        const card = document.createElement('div');
        card.className = `radar-card${matchingPos ? ' has-position' : ''}${t.muted ? ' muted' : ''}`;
        card.dataset.symbol = t.symbol;
        card.innerHTML = `
            <div class="radar-card-top">
                <span class="radar-ticker">${escapeHtml(t.symbol)}${signalDot}</span>
                <span class="radar-change" style="color:${changeColor}">${changeSign}${change.toFixed(1)}%</span>
            </div>
            <div class="radar-card-mid">
                <div class="radar-rvol-bar"><div class="radar-rvol-fill" style="width:${rvolBar}%"></div></div>
                <span class="radar-zone-pip" style="background:${zonePipColor}" title="${escapeHtml(zone)}"></span>
            </div>
            ${positionLabel}
        `;
        card.addEventListener('click', () => analyzeTicker(t.symbol));
        list.appendChild(card);
    });
}

function setupBulkActions() {
    const muteBtn = document.getElementById('bulk-mute');
    const unmuteBtn = document.getElementById('bulk-unmute');
    const removeBtn = document.getElementById('bulk-remove');
    const cancelBtn = document.getElementById('bulk-cancel');

    if (muteBtn) muteBtn.addEventListener('click', () => bulkMuteTickers(true));
    if (unmuteBtn) unmuteBtn.addEventListener('click', () => bulkMuteTickers(false));
    if (removeBtn) removeBtn.addEventListener('click', bulkRemoveTickers);
    if (cancelBtn) cancelBtn.addEventListener('click', () => {
        selectedTickers.clear();
        renderTickerList();
        updateBulkActions();
    });
}

function updateBulkActions() {
    const bulkBar = document.getElementById('bulk-actions');
    const countEl = document.getElementById('bulk-count');
    if (!bulkBar || !countEl) return;
    const count = selectedTickers.size;
    countEl.textContent = `${count} selected`;
    bulkBar.style.display = count > 0 ? 'flex' : 'none';
}

async function toggleMuteTicker(symbol, muted) {
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/${encodeURIComponent(symbol)}/mute`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({ muted })
        });
        const data = await response.json();
        if (data.status === 'success') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Failed to update mute status');
        }
    } catch (error) {
        console.error('Mute toggle failed:', error);
    }
}

async function bulkMuteTickers(muted) {
    if (selectedTickers.size === 0) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/bulk-mute`, {
            method: 'PATCH',
            headers: authHeaders(),
            body: JSON.stringify({ symbols: Array.from(selectedTickers), muted })
        });
        const data = await response.json();
        if (data.status === 'success') {
            selectedTickers.clear();
            fetchTickerList(true);
            updateBulkActions();
        } else {
            alert(data.message || 'Bulk update failed');
        }
    } catch (error) {
        console.error('Bulk mute failed:', error);
    }
}

async function bulkRemoveTickers() {
    if (selectedTickers.size === 0) return;
    if (!confirm('Remove selected tickers?')) return;
    const symbols = Array.from(selectedTickers);
    await Promise.all(symbols.map(symbol => deleteTicker(symbol, false)));
    selectedTickers.clear();
    fetchTickerList(true);
    updateBulkActions();
}

async function deleteTicker(symbol, confirmDelete = true) {
    if (confirmDelete && !confirm(`Remove ${symbol} from watchlist?`)) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/${encodeURIComponent(symbol)}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': API_KEY }
        });
        const data = await response.json();
        if (data.status === 'success') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Remove failed');
        }
    } catch (error) {
        console.error('Delete ticker failed:', error);
    }
}

// Helper functions for watchlist actions
function analyzeTicker(ticker) {
    const input = document.getElementById('analyzeTickerInput');
    const btn = document.getElementById('analyzeTickerBtn');
    if (input && ticker) input.value = ticker;
    if (btn) btn.click();
}

function openTickerChart(ticker) {
    if (typeof changeChartSymbol === 'function') {
        changeChartSymbol(ticker);
        return;
    }
    if (typeof tvWidget !== 'undefined' && tvWidget.setSymbol) {
        tvWidget.setSymbol(ticker, '1D');
        return;
    }
    window.open(`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(ticker)}`, '_blank');
}

// ==========================================
// SINGLE TICKER ANALYZER (Unified)
// ==========================================

function initTickerAnalyzer() {
    const analyzeBtn = document.getElementById('analyzeTickerBtn');
    const analyzeInput = document.getElementById('analyzeTickerInput');
    const addBtn = document.getElementById('addToWatchlistBtn');

    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', runUnifiedAnalyzer);
    }

    if (analyzeInput) {
        analyzeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                runUnifiedAnalyzer();
            }
        });
    }

    if (addBtn) {
        addBtn.addEventListener('click', addAnalyzedTickerToWatchlist);
    }
}

async function runUnifiedAnalyzer() {
    const input = document.getElementById('analyzeTickerInput');
    const resultsContainer = document.getElementById('analyzerResultsV3');
    const addBtn = document.getElementById('addToWatchlistBtn');
    const ticker = input ? input.value.trim().toUpperCase() : '';
    if (!ticker || !resultsContainer) return;
    lastAnalyzedTicker = ticker;
    if (addBtn) addBtn.disabled = true;
    resultsContainer.innerHTML = '<p class="empty-state">Analyzing...</p>';
    try {
        const [analysisResp, signalsResp] = await Promise.all([
            fetch(`${API_URL}/analyze/${encodeURIComponent(ticker)}`),
            fetch(`${API_URL}/analyze/${encodeURIComponent(ticker)}/signals?days=14`)
        ]);
        const analysisData = await analysisResp.json();
        const signalsData = await signalsResp.json().catch(() => ({ signals: [] }));
        if (analysisData.status === 'success') {
            renderAnalyzerV4(analysisData.analysis || {}, signalsData.signals || [], ticker);
            if (addBtn) addBtn.disabled = false;
            openTickerChart(ticker);
        } else {
            resultsContainer.innerHTML = `<p class="empty-state">${analysisData.message || 'Analysis failed'}</p>`;
        }
    } catch (error) {
        console.error('Analyzer error:', error);
        resultsContainer.innerHTML = '<p class="empty-state">Analysis failed</p>';
    }
}

function renderAnalyzerV4(analysis, recentSignals, ticker) {
    const container = document.getElementById('analyzerResultsV3');
    if (!container) return;
    const cta = analysis.cta || {};
    const ctaAnalysis = cta.cta_analysis || {};
    const tech = analysis.technicals || {};
    const fund = analysis.fundamentals || {};
    const trapped = analysis.trapped_traders || {};
    const techScore = tech.score || 0;
    const ctaScore = ctaAnalysis.cta_zone === 'MAX_LONG' ? 85
                   : ctaAnalysis.cta_zone === 'RISK_ON' ? 70
                   : ctaAnalysis.cta_zone === 'NEUTRAL' ? 50
                   : ctaAnalysis.cta_zone === 'RISK_OFF' ? 30
                   : ctaAnalysis.cta_zone === 'CAPITULATION' ? 15 : 50;
    const compositeScore = Math.round((ctaScore + (techScore * 50 + 50)) / 2);
    const scoreColor = compositeScore >= 70 ? '#00e676'
                     : compositeScore >= 50 ? '#ff9800' : '#e5370e';
    const zone = ctaAnalysis.cta_zone || 'UNKNOWN';
    const zonePill = zone.includes('LONG') ? 'good' : zone.includes('CAPIT') || zone.includes('WATER') ? 'bad' : 'neutral';
    const signalsHtml = recentSignals.length > 0
        ? recentSignals.slice(0, 8).map(s => {
            const ago = getTimeAgo(new Date(s.created_at));
            const dirClass = (s.direction || '').toLowerCase();
            return `<div class="analyzer-signal-row ${dirClass}">
                <span class="analyzer-sig-strategy">${escapeHtml(formatStrategyName(s.strategy || ''))}</span>
                <span class="analyzer-sig-dir ${dirClass}">${s.direction || '-'}</span>
                <span class="analyzer-sig-score">${Math.round(s.score || 0)}</span>
                <span class="analyzer-sig-status">${s.status || '-'}</span>
                <span class="analyzer-sig-time">${ago}</span>
            </div>`;
        }).join('')
        : '<p class="empty-state" style="font-size:11px;">No signals in 14 days</p>';
    const tvSignal = tech.signal || 'N/A';
    const tvSignalClass = tvSignal === 'BUY' ? 'good' : tvSignal === 'SELL' ? 'bad' : 'neutral';
    const analystRating = fund.analyst?.rating || 'N/A';
    const priceTarget = fund.price_target?.target;
    const upside = fund.price_target?.upside_pct;
    const trappedVerdict = trapped.verdict || 'NO_SIGNAL';
    const trappedClass = trappedVerdict.includes('BULL') ? 'good' : trappedVerdict.includes('BEAR') ? 'bad' : 'neutral';
    container.innerHTML = `
        <div class="analyzer-v4-header">
            <div class="analyzer-v4-ticker-info">
                <span class="analyzer-v4-ticker">${escapeHtml(ticker)}</span>
                <span class="analyzer-v4-price">$${ctaAnalysis.current_price?.toFixed(2) || '--'}</span>
                <span class="analyzer-v4-zone analysis-pill ${zonePill}">${escapeHtml(zone)}</span>
            </div>
            <div class="analyzer-v4-score-ring" style="--score-color: ${scoreColor}; --score-pct: ${compositeScore}%;">
                <span class="score-number">${compositeScore}</span>
            </div>
        </div>
        <div class="analyzer-v4-columns">
            <div class="analyzer-v4-col">
                <div class="analyzer-v4-col-title">Technical</div>
                <div class="analyzer-v4-item"><span class="item-label">TV Signal</span><span class="analysis-pill ${tvSignalClass}">${escapeHtml(tvSignal)}</span></div>
                <div class="analyzer-v4-item"><span class="item-label">Trapped</span><span class="analysis-pill ${trappedClass}">${escapeHtml(trappedVerdict)}</span></div>
                <div class="analyzer-v4-item"><span class="item-label">SMA 20/50/120</span><span class="item-value">${ctaAnalysis.sma20?.toFixed(0) || '-'} / ${ctaAnalysis.sma50?.toFixed(0) || '-'} / ${ctaAnalysis.sma120?.toFixed(0) || '-'}</span></div>
                <div class="analyzer-v4-item"><span class="item-label">ATR</span><span class="item-value">$${ctaAnalysis.atr?.toFixed(2) || '-'}</span></div>
            </div>
            <div class="analyzer-v4-col">
                <div class="analyzer-v4-col-title">Flow & Signals</div>
                <div class="analyzer-v4-signals-panel">${signalsHtml}</div>
            </div>
            <div class="analyzer-v4-col">
                <div class="analyzer-v4-col-title">Fundamentals</div>
                <div class="analyzer-v4-item"><span class="item-label">Analyst Rating</span><span class="item-value">${escapeHtml(analystRating)}</span></div>
                <div class="analyzer-v4-item"><span class="item-label">Price Target</span><span class="item-value">${priceTarget ? '$' + priceTarget : '-'}</span></div>
                <div class="analyzer-v4-item"><span class="item-label">Upside</span><span class="item-value">${upside ? upside + '%' : '-'}</span></div>
            </div>
        </div>
        <div class="analyzer-v4-olympus">
            <button class="olympus-btn" id="olympusAnalyzeBtn" data-ticker="${escapeHtml(ticker)}">Olympus Analysis (~$0.02)</button>
            <div class="olympus-results" id="olympusResults" style="display:none;"></div>
        </div>
    `;
    const olympusBtn = document.getElementById('olympusAnalyzeBtn');
    if (olympusBtn) olympusBtn.addEventListener('click', () => runOlympusAnalysis(ticker));
}

async function runOlympusAnalysis(ticker) {
    const btn = document.getElementById('olympusAnalyzeBtn');
    const results = document.getElementById('olympusResults');
    if (!btn || !results) return;
    btn.disabled = true;
    btn.textContent = 'Committee convening...';
    results.style.display = 'block';
    results.innerHTML = '<p class="empty-state">Running 4-agent analysis (~40s)...</p>';
    try {
        const response = await fetch(`${API_URL}/analyze/${encodeURIComponent(ticker)}/olympus`, {
            method: 'POST',
            headers: authHeaders()
        });
        if (response.status === 429) {
            results.innerHTML = '<p class="empty-state">Rate limited -- try again in a few minutes</p>';
            return;
        }
        const data = await response.json();
        if (data.olympus) {
            const o = data.olympus;
            const cached = data.cached ? ' (cached)' : '';
            results.innerHTML = `
                <div class="olympus-header">Olympus Analysis${cached}</div>
                <div class="olympus-agents">
                    <div class="olympus-agent toro">
                        <div class="agent-name">TORO <span class="agent-conviction">${escapeHtml(o.toro?.conviction || '-')}</span></div>
                        <div class="agent-summary">${escapeHtml(o.toro?.summary || 'No analysis')}</div>
                    </div>
                    <div class="olympus-agent ursa">
                        <div class="agent-name">URSA <span class="agent-conviction">${escapeHtml(o.ursa?.conviction || '-')}</span></div>
                        <div class="agent-summary">${escapeHtml(o.ursa?.summary || 'No analysis')}</div>
                    </div>
                    <div class="olympus-agent risk">
                        <div class="agent-name">RISK</div>
                        <div class="agent-summary">Entry: ${escapeHtml(o.risk?.entry || '-')} | Stop: ${escapeHtml(o.risk?.stop || '-')} | Target: ${escapeHtml(o.risk?.target || '-')}</div>
                    </div>
                    <div class="olympus-agent pivot">
                        <div class="agent-name">PIVOT <span class="agent-action ${(o.pivot?.action || '').toLowerCase()}">${escapeHtml(o.pivot?.action || '-')}</span> <span class="agent-conviction">${escapeHtml(o.pivot?.conviction || '-')}</span></div>
                        <div class="agent-summary">${escapeHtml(o.pivot?.synthesis || 'No synthesis')}</div>
                        ${o.pivot?.invalidation ? `<div class="agent-invalidation">Invalidation: ${escapeHtml(o.pivot.invalidation)}</div>` : ''}
                    </div>
                </div>
            `;
        } else {
            results.innerHTML = `<p class="empty-state">${data.error || 'Analysis failed'}</p>`;
        }
    } catch (error) {
        console.error('Olympus analysis error:', error);
        results.innerHTML = '<p class="empty-state">Olympus analysis failed</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Olympus Analysis (~$0.02)';
    }
}

async function addAnalyzedTickerToWatchlist() {
    if (!lastAnalyzedTicker) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/add`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ symbol: lastAnalyzedTicker, notes: 'Added from Analyzer' })
        });
        const data = await response.json();
        if (data.status === 'success' || data.status === 'already_exists') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Failed to add ticker');
        }
    } catch (error) {
        console.error('Add to watchlist failed:', error);
    }
}


// ==========================================
// STRATEGY CONTROLS
// ==========================================

let strategiesData = {};

function initStrategies() {
    const enableAllBtn = document.getElementById('enableAllBtn');
    const disableAllBtn = document.getElementById('disableAllBtn');
    
    if (enableAllBtn) {
        enableAllBtn.addEventListener('click', enableAllStrategies);
    }
    
    if (disableAllBtn) {
        disableAllBtn.addEventListener('click', disableAllStrategies);
    }
    
    loadStrategies();
}

async function loadStrategies() {
    try {
        const response = await fetch(`${API_URL}/strategies`);
        const data = await response.json();
        
        if (data.status === 'success') {
            strategiesData = data.strategies;
            renderStrategies();
        }
    } catch (error) {
        console.error('Error loading strategies:', error);
        document.getElementById('strategiesGrid').innerHTML = 
            '<p class="empty-state">Failed to load strategies</p>';
    }
}

function renderStrategies() {
    const container = document.getElementById('strategiesGrid');
    
    if (!container) return;
    
    const strategyIds = Object.keys(strategiesData);
    
    if (strategyIds.length === 0) {
        container.innerHTML = '<p class="empty-state">No strategies configured</p>';
        return;
    }
    
    container.innerHTML = strategyIds.map(id => {
        const strategy = strategiesData[id];
        const enabled = strategy.enabled;
        const category = strategy.category || 'other';
        
        return `
            <div class="strategy-card ${enabled ? 'enabled' : 'disabled'}" data-strategy-id="${id}">
                <div class="strategy-card-header">
                    <span class="strategy-name">${strategy.name}</span>
                    <label class="strategy-toggle">
                        <input type="checkbox" ${enabled ? 'checked' : ''} data-strategy-id="${id}">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="strategy-description">${strategy.description}</div>
                <div class="strategy-meta">
                    <span class="strategy-badge ${category}">${category}</span>
                    ${strategy.timeframes ? strategy.timeframes.map(tf => 
                        `<span class="strategy-badge">${tf}</span>`
                    ).join('') : ''}
                </div>
            </div>
        `;
    }).join('');
    
    // Attach toggle events
    container.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            toggleStrategy(e.target.dataset.strategyId, e.target.checked);
        });
    });
}

async function toggleStrategy(strategyId, enabled) {
    try {
        const response = await fetch(`${API_URL}/strategies/${strategyId}/toggle`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ enabled })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Update local state
            strategiesData[strategyId].enabled = enabled;
            
            // Update card styling
            const card = document.querySelector(`.strategy-card[data-strategy-id="${strategyId}"]`);
            if (card) {
                card.classList.toggle('enabled', enabled);
                card.classList.toggle('disabled', !enabled);
            }
            
            console.log(`Strategy ${strategyId} ${enabled ? 'enabled' : 'disabled'}`);
        }
    } catch (error) {
        console.error('Error toggling strategy:', error);
        // Revert checkbox
        const checkbox = document.querySelector(`input[data-strategy-id="${strategyId}"]`);
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

async function enableAllStrategies() {
    try {
        const response = await fetch(`${API_URL}/strategies/enable-all`, {
            method: 'POST',
            headers: { 'X-API-Key': API_KEY }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadStrategies();
            console.log('All strategies enabled');
        }
    } catch (error) {
        console.error('Error enabling all strategies:', error);
    }
}

async function disableAllStrategies() {
    if (!confirm('KILL SWITCH: This will disable ALL strategies. Continue?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/strategies/disable-all`, {
            method: 'POST',
            headers: { 'X-API-Key': API_KEY }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadStrategies();
            console.log('ðŸ›‘ All strategies DISABLED');
        }
    } catch (error) {
        console.error('Error disabling all strategies:', error);
    }
}

// Initialize strategies on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initStrategies, 800);
    setTimeout(initCtaScanner, 900);
    setTimeout(initBtcSignals, 1000);
});


// ==========================================
// CTA SCANNER (Equity Swing Trading)
// ==========================================

let ctaResults = {
    goldenTouch: [],
    twoClose: [],
    pullback: [],
    zoneUpgrade: []
};

let ctaZones = {};

function initCtaScanner() {
    const runCtaScanBtn = document.getElementById('runCtaScanBtn');
    if (runCtaScanBtn) {
        runCtaScanBtn.addEventListener('click', runCtaScan);
    }
    
    // Load CTA zone data for watchlist tickers
    loadCtaZones();
}

async function loadCtaZones() {
    const watchlistTickers = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA'];
    const zoneCardsContainer = document.getElementById('ctaZoneCards');
    
    if (!zoneCardsContainer) return;
    
    for (const ticker of watchlistTickers) {
        try {
            const response = await fetch(`${API_URL}/cta/analyze/${ticker}`);
            const data = await response.json();
            
            if (data.cta_analysis) {
                ctaZones[ticker] = data.cta_analysis;
            }
        } catch (error) {
            console.error(`Error loading CTA zone for ${ticker}:`, error);
        }
    }
    
    renderCtaZones();
}

function renderCtaZones() {
    const container = document.getElementById('ctaZoneCards');
    if (!container) return;
    
    const tickers = Object.keys(ctaZones);
    
    if (tickers.length === 0) {
        container.innerHTML = `
            <div class="cta-zone-card">
                <span class="zone-ticker">SPY</span>
                <span class="zone-status loading">Loading...</span>
            </div>
        `;
        return;
    }
    
    container.innerHTML = tickers.map(ticker => {
        const zone = ctaZones[ticker];
        const zoneStatus = zone.cta_zone || 'UNKNOWN';
        const zoneDisplay = zoneStatus.replace('_', ' ');
        const zoneWithKb = wrapWithKbLink(zoneStatus);
        
        return `
            <div class="cta-zone-card ${zoneStatus}" data-ticker="${ticker}">
                <span class="zone-ticker">${ticker}</span>
                <span class="zone-status ${zoneStatus}">${zoneWithKb}</span>
            </div>
        `;
    }).join('');
    
    // Attach KB handlers
    attachDynamicKbHandlers(container);
    
    // Attach click events to view on chart (but not on KB links)
    container.querySelectorAll('.cta-zone-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't change chart if clicking a KB link
            if (e.target.classList.contains('kb-term-dynamic')) return;
            const ticker = card.dataset.ticker;
            changeChartSymbol(ticker);
        });
    });
}

async function runCtaScan() {
    const btn = document.getElementById('runCtaScanBtn');
    const status = document.getElementById('ctaScanStatus');
    
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    status.textContent = 'Scanning watchlist + S&P 500...';
    status.classList.add('scanning');
    
    try {
        const response = await fetch(`${API_URL}/cta/scan?include_watchlist=true`);
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Store results by signal type
        ctaResults.goldenTouch = data.golden_touch_signals || [];
        ctaResults.twoClose = data.two_close_signals || [];
        ctaResults.pullback = data.pullback_signals || [];
        ctaResults.zoneUpgrade = data.zone_upgrade_signals || [];
        
        renderCtaResults();
        
        status.textContent = `Found ${data.total_signals} signals`;
        status.classList.remove('scanning');
        
    } catch (error) {
        console.error('CTA scan error:', error);
        status.textContent = 'Scan failed';
        status.classList.remove('scanning');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Scan';
    }
}

function renderCtaResults() {
    renderCtaColumn('goldenSignals', 'goldenCount', ctaResults.goldenTouch, 'Rare: 120 SMA first touch');
    renderCtaColumn('twoCloseSignals', 'twoCloseCount', ctaResults.twoClose, 'No confirmed breakouts');
    renderCtaColumn('pullbackSignals', 'pullbackCount', ctaResults.pullback, 'No pullbacks to 20 SMA');
}

function renderCtaColumn(containerId, countId, signals, emptyMessage) {
    const container = document.getElementById(containerId);
    const countEl = document.getElementById(countId);
    
    if (!container) return;
    
    countEl.textContent = signals.length;
    
    if (signals.length === 0) {
        container.innerHTML = `<p class="empty-state">${emptyMessage}</p>`;
        return;
    }
    
    container.innerHTML = signals.slice(0, 5).map(signal => createCtaCard(signal)).join('');
    
    // Attach KB handlers
    attachDynamicKbHandlers(container);
    
    // Attach click events
    container.querySelectorAll('.cta-ticker').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            changeChartSymbol(e.target.dataset.symbol);
        });
    });
}

function createCtaCard(signal) {
    const setup = signal.setup || {};
    const context = signal.context || {};
    const zoneWithKb = wrapWithKbLink(context.cta_zone || 'Unknown');
    
    return `
        <div class="cta-card" data-symbol="${signal.symbol}">
            <div class="cta-card-header">
                <span class="cta-ticker" data-symbol="${signal.symbol}">${signal.symbol}</span>
                <span class="cta-score">${signal.priority}</span>
            </div>
            <div class="cta-card-body">
                <div class="cta-metric">
                    <div class="cta-metric-label">Entry</div>
                    <div class="cta-metric-value">$${setup.entry?.toFixed(2) || '-'}</div>
                </div>
                <div class="cta-metric">
                    <div class="cta-metric-label">Stop</div>
                    <div class="cta-metric-value">$${setup.stop?.toFixed(2) || '-'}</div>
                </div>
                <div class="cta-metric">
                    <div class="cta-metric-label">R:R</div>
                    <div class="cta-metric-value">${formatRiskReward(setup.rr_ratio)}</div>
                </div>
            </div>
            <div class="cta-card-footer">
                Zone: ${zoneWithKb} | Vol: ${context.volume_ratio?.toFixed(1) || '-'}x
            </div>
        </div>
    `;
}



// Enhanced Analyzer with Context Cards
async function analyzeTickerEnhanced(ticker) {
    const contextContainer = document.getElementById('analyzerContext');
    if (!contextContainer) return;

    try {
        // Show context section
        contextContainer.style.display = 'grid';

        // Fetch all data in parallel
        const [ctaResponse, sectorResponse, biasResponse, flowResponse, priceResponse] = await Promise.all([
            fetch(`${API_URL}/cta/analyze/${ticker}`),
            fetch(`${API_URL}/hybrid/combined/${ticker}`),
            fetch(`${API_URL}/bias/composite`),
            fetch(`${API_URL}/flow/ticker/${ticker}`),
            fetch(`${API_URL}/hybrid/price/${ticker}`)
        ]);

        const ctaData = await ctaResponse.json();
        const sectorData = await sectorResponse.json();
        const biasData = await biasResponse.json();
        const flowData = await flowResponse.json();
        const priceData = await priceResponse.json();

        // Populate CTA Zone Card
        const ctaAnalysis = ctaData.cta_analysis || {};
        const zoneStatus = document.getElementById('contextZoneStatus');
        const zoneSMAs = document.getElementById('contextZoneSMAs');

        if (zoneStatus) {
            const zoneLabel = ctaAnalysis.cta_zone || 'UNKNOWN';
            let zoneClass = 'zone-neutral';
            if (zoneLabel === 'MAX_LONG') zoneClass = 'zone-max-long';
            else if (zoneLabel === 'RISK_ON') zoneClass = 'zone-risk-on';
            else if (zoneLabel === 'NEUTRAL') zoneClass = 'zone-neutral';
            else if (zoneLabel === 'RISK_OFF') zoneClass = 'zone-risk-off';
            else if (zoneLabel === 'CAPITULATION') zoneClass = 'zone-capitulation';

            zoneStatus.innerHTML = `<span class="zone-label ${zoneClass}">${zoneLabel}</span>`;
        }

        if (zoneSMAs) {
            document.getElementById('sma20').textContent = ctaAnalysis.sma20 ? `$${ctaAnalysis.sma20.toFixed(2)}` : '--';
            document.getElementById('sma50').textContent = ctaAnalysis.sma50 ? `$${ctaAnalysis.sma50.toFixed(2)}` : '--';
            document.getElementById('sma120').textContent = ctaAnalysis.sma120 ? `$${ctaAnalysis.sma120.toFixed(2)}` : '--';
        }

        // Populate Sector Info Card
        const meta = sectorData.metadata || {};
        document.getElementById('sectorName').textContent = meta.sector || '--';
        document.getElementById('sectorETF').textContent = meta.sector_etf || '--';

        // Populate Bias Alignment Card
        const dailyBias = biasData?.data?.daily?.level || '';
        const dailyIsToro = dailyBias.includes('TORO');

        const longAlignment = document.getElementById('longAlignment');
        const shortAlignment = document.getElementById('shortAlignment');

        if (longAlignment) {
            longAlignment.textContent = dailyIsToro ? 'Aligned' : 'Divergent';
            longAlignment.className = 'alignment-status ' + (dailyIsToro ? 'aligned' : 'divergent');
        }

        if (shortAlignment) {
            shortAlignment.textContent = !dailyIsToro ? 'Aligned' : 'Divergent';
            shortAlignment.className = 'alignment-status ' + (!dailyIsToro ? 'aligned' : 'divergent');
        }

        // Populate Risk Levels Card
        const price = priceData.price || 0;
        const atr = ctaAnalysis.atr || 0;

        document.getElementById('atrValue').textContent = atr ? `$${atr.toFixed(2)}` : '--';
        document.getElementById('stopDistance').textContent = atr ? `$${(atr * 2).toFixed(2)}` : '--';
        document.getElementById('targetDistance').textContent = atr ? `$${(atr * 3).toFixed(2)}` : '--';

        // Populate Recent Flow Card
        const flowSummary = document.getElementById('contextFlowSummary');
        if (flowData.flow && flowData.flow.length > 0) {
            const recentFlow = flowData.flow.slice(0, 3);
            flowSummary.innerHTML = recentFlow.map(f => `
                <div class="flow-item">
                    <span class="flow-direction ${f.sentiment === 'BULLISH' ? 'bullish' : 'bearish'}">
                        ${f.sentiment === 'BULLISH' ? 'BULL' : 'BEAR'} ${f.type}
                    </span>
                    <span class="flow-score">${f.notability_score}/100</span>
                </div>
            `).join('');
        } else {
            flowSummary.innerHTML = '<p class="flow-empty">No recent flow data</p>';
        }

        // Recent Signals Card — per-ticker signal endpoint removed (Phase 0D)
        const signalsSummary = document.getElementById('contextSignalsSummary');
        if (signalsSummary) {
            signalsSummary.innerHTML = '<p class="signals-empty">No per-ticker signal data</p>';
        }

        // Wire up action buttons
        const createIdeaBtn = document.getElementById('createTradeIdeaBtn');
        const addWatchlistBtn = document.getElementById('addToWatchlistBtn');

        if (createIdeaBtn) {
            createIdeaBtn.onclick = () => {
                console.log('Create trade idea for', ticker);
                // This would open a modal or navigate to trade idea creation
            };
        }

        if (addWatchlistBtn) {
            addWatchlistBtn.onclick = () => {
                addTickerToWatchlist(ticker);
            };
        }

    } catch (error) {
        console.error('Error in enhanced analyzer:', error);
        contextContainer.style.display = 'none';
    }
}


// ==========================================
// BTC BOTTOM SIGNALS DASHBOARD (ALL 9 AUTOMATED)
// ==========================================

let btcSignals = {};
let btcConfluence = {};
let btcRawData = {};
let btcApiStatus = {};
let btcApiKeys = {};
let btcApiErrors = {};

function getBtcUiTargets() {
    return [
        {
            summary: document.getElementById('btcConfluenceSummary'),
            apiStatus: document.getElementById('btcApiStatus'),
            grid: document.getElementById('btcSignalsGrid')
        },
        {
            summary: document.getElementById('cryptoBtcConfluenceSummary'),
            apiStatus: document.getElementById('cryptoBtcApiStatus'),
            grid: document.getElementById('cryptoBtcSignalsGrid')
        }
    ];
}

function initBtcSignals() {
    const hasBtcPanels = document.getElementById('btcSignalsGrid') || document.getElementById('cryptoBtcSignalsGrid');
    const sessionPill = document.getElementById('cryptoSessionStatus');
    if (!hasBtcPanels) {
        if (sessionPill) {
            loadBtcSessions();
            setInterval(loadBtcSessions, 10 * 60 * 1000);
        }
        return;
    }
    const refreshButtons = document.querySelectorAll('.btc-refresh-btn');
    const resetButtons = document.querySelectorAll('.btc-reset-btn');

    refreshButtons.forEach(btn => {
        if (!btn.dataset.label) {
            btn.dataset.label = btn.textContent.trim();
        }
        btn.addEventListener('click', refreshBtcSignals);
    });

    resetButtons.forEach(btn => {
        btn.addEventListener('click', resetBtcSignals);
    });
    
    // Initial load
    loadBtcSignals();
    loadBtcSessions();

    // Auto-refresh: signals every 5 min, sessions every 10 min
    setInterval(loadBtcSignals, 5 * 60 * 1000);
    setInterval(loadBtcSessions, 10 * 60 * 1000);
}

async function loadBtcSessions() {
    await renderBtcSessions();
}

async function renderBtcSessions() {
    const listEl = document.getElementById('cryptoBtcSessionList');
    const currentEl = document.getElementById('cryptoBtcSessionCurrent');
    const sessionPill = document.getElementById('cryptoSessionStatus');
    if (!listEl && !currentEl && !sessionPill) return;

    try {
        const response = await fetch(`${API_URL}/btc/sessions`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        const sessions = data.sessions || {};
        const currentSession = data.current_session || null;
        const resolvedSession = resolveActiveSession(currentSession, sessions);

        // Update the session pill in the bias bar
        updateCryptoSessionStatus(resolvedSession, sessions);

        // Update the current-session indicator inside the crypto panel.
        // The active styling is on .btc-session-current.active â€” toggle that class on the element.
        if (currentEl) {
            if (resolvedSession && resolvedSession.active) {
                currentEl.classList.add('active');
                currentEl.innerHTML = `<span class="session-status">NOW: ${escapeHtml(resolvedSession.name)}</span>`;
            } else {
                currentEl.classList.remove('active');
                const nextSession = getNextSessionBySchedule(sessions);
                const nextName = nextSession ? nextSession.name : null;
                currentEl.innerHTML = `<span class="session-status">No active session${nextName ? ` &middot; Next: ${escapeHtml(nextName)}` : ''}</span>`;
            }
        }

        // Render session list rows
        if (listEl) {
            const sessionIds = Object.keys(sessions);
            if (sessionIds.length === 0) {
                listEl.innerHTML = '<p class="empty-state">No sessions configured</p>';
                return;
            }
            listEl.innerHTML = sessionIds.map(id => {
                const s = sessions[id];
                const isActive = resolvedSession && resolvedSession.name === s.name;
                const localTime = s.utc_time ? formatUtcRangeToDenver(s.utc_time) : '';
                return `
                    <div class="btc-session-item${isActive ? ' active' : ''}">
                        <div class="session-name${isActive ? ' active' : ''}">${escapeHtml(s.name)}</div>
                        <div class="session-time">${escapeHtml(s.ny_time)} ET${localTime ? ` &middot; ${escapeHtml(localTime)}` : ''}</div>
                        <div class="session-note">${escapeHtml(s.trading_note || '')}</div>
                    </div>
                `;
            }).join('');
        }
    } catch (err) {
        console.error('Error loading BTC sessions:', err);
        if (listEl) listEl.innerHTML = '<p class="empty-state">Could not load sessions</p>';
        if (sessionPill) {
            sessionPill.innerHTML = '<span class="session-pill neutral">Session data unavailable</span>';
        }
    }
}

async function loadBtcSignals() {
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        btcApiKeys = data.api_keys || {};
        btcApiErrors = data.api_errors || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error loading BTC signals:', error);
        getBtcUiTargets().forEach(target => {
            if (target.grid) {
                target.grid.innerHTML = '<p class="empty-state">Failed to load signals</p>';
            }
        });
    }
}

async function refreshBtcSignals() {
    const refreshButtons = document.querySelectorAll('.btc-refresh-btn');
    refreshButtons.forEach(btn => {
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
    });
    
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals/refresh`, {
            method: 'POST',
            headers: { 'X-API-Key': API_KEY }
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        btcApiKeys = data.api_keys || {};
        btcApiErrors = data.api_errors || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error refreshing BTC signals:', error);
    } finally {
        refreshButtons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.dataset.label || ' Refresh';
        });
    }
}

function renderBtcSummary() {
    const firingCount = btcConfluence.firing || 0;
    const totalSignals = btcConfluence.total || 9;
    const verdict = btcConfluence.verdict || 'Checking signals...';
    const verdictLevel = btcConfluence.verdict_level || 'none';
    const bullishConfluence = firingCount >= 5 || verdictLevel === 'strong' || verdictLevel === 'moderate';

    getBtcUiTargets().forEach(target => {
        if (!target.summary) return;
        target.summary.innerHTML = `
            <div class="confluence-meter">
                <span class="confluence-count">${firingCount}/${totalSignals}</span>
                <span class="confluence-label">Signals Firing</span>
            </div>
            <div class="confluence-verdict ${verdictLevel}">${verdict}</div>
        `;

        const panel = target.summary.closest('.btc-signals-section, .crypto-btc-signals-panel');
        if (panel) {
            panel.classList.toggle('confluence-bullish', bullishConfluence);
        }
    });
}

function renderBtcApiStatus() {
    const apis = [
        { key: 'coinalyze', name: 'Coinalyze', signals: 'Funding, OI, Liqs, Term' },
        { key: 'deribit', name: 'Deribit', signals: '25d Skew' },
        { key: 'defillama', name: 'DeFiLlama', signals: 'Stablecoin APR' },
        { key: 'binance', name: 'Binance', signals: 'Orderbook, Basis' },
        { key: 'yfinance', name: 'yfinance', signals: 'VIX' }
    ];

    getBtcUiTargets().forEach(target => {
        if (!target.apiStatus) return;
        target.apiStatus.innerHTML = apis.map(api => {
            const available = !!btcApiStatus[api.key];
            const keyMissing = api.key === 'coinalyze' && btcApiKeys.coinalyze === false;
            const status = keyMissing ? 'key-missing' : (available ? 'connected' : 'disconnected');
            return `
                <span class="api-status-item ${status}" title="${api.signals}">
                    ${api.name}: ${status === 'connected' ? 'OK' : status === 'key-missing' ? 'KEY' : 'OFF'}
                </span>
            `;
        }).join('');
    });
}

function renderBtcSignals() {
    const signalIds = Object.keys(btcSignals);

    getBtcUiTargets().forEach(target => {
        if (!target.grid) return;
        if (signalIds.length === 0) {
            target.grid.innerHTML = '<p class="empty-state">No signals configured</p>';
            return;
        }

        target.grid.innerHTML = signalIds.map(id => {
        const signal = btcSignals[id];
        const status = signal.status || 'UNKNOWN';
        const isAuto = signal.auto !== false;
        const hasManualOverride = signal.manual_override === true;
        
        // Format timestamp
        let timestamp = '';
        if (signal.updated_at) {
            const date = new Date(signal.updated_at);
            timestamp = date.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit',
                timeZone: 'America/New_York'
            }) + ' ET';
        }
        
        // KB link for signal name
        const nameWithKb = `<span class="kb-term-dynamic" data-kb-term="btc-bottom-signals">${signal.name}</span>`;
        
        // Source indicator (ASCII only to avoid encoding artifacts)
        const sourceLabel = isAuto ? 'AUTO' : 'MANUAL';
        
        // Value display - use raw value if available and detailed
        const rawData = btcRawData[id] || {};
        const apiError = rawData.error || btcApiErrors[id];
        let displayValue = signal.value;
        if (displayValue === null || displayValue === undefined) {
            displayValue = '--';
        }
        
        return `
            <div class="btc-signal-card ${status} ${isAuto ? 'auto' : 'manual'}" data-signal-id="${id}">
                <div class="btc-signal-header">
                    <span class="btc-signal-name">${nameWithKb}</span>
                    <span class="btc-signal-status ${status}">${status}</span>
                </div>
                <div class="btc-signal-value-display">
                    <span class="signal-value-main">${displayValue}</span>
                </div>
                <div class="btc-signal-description">${signal.description}</div>
                ${apiError ? `<div class=\"btc-signal-error\">${escapeHtml(apiError)}</div>` : ''}
                <div class="btc-signal-footer">
                    <span class="btc-signal-source ${isAuto ? 'auto' : 'manual'}">${sourceLabel}</span>
                    <span class="btc-signal-timestamp">${timestamp}</span>
                </div>
                ${hasManualOverride ? '<div class="manual-override-badge">Override Active</div>' : ''}
            </div>
        `;
    }).join('');
    
        // Attach KB handlers
        attachDynamicKbHandlers(target.grid);
        
        // Attach click events for manual override toggle
        target.grid.querySelectorAll('.btc-signal-card').forEach(card => {
            card.addEventListener('click', (e) => {
                // Don't toggle if clicking a KB link
                if (e.target.classList.contains('kb-term-dynamic')) return;
                toggleBtcSignal(card.dataset.signalId);
            });
        });
    });
}

async function toggleBtcSignal(signalId) {
    const signal = btcSignals[signalId];
    if (!signal) return;
    
    const isAuto = signal.auto !== false;
    const hasManualOverride = signal.manual_override === true;
    
    // If currently has manual override, clear it
    if (hasManualOverride) {
        if (confirm('Clear manual override and return to auto-fetch?')) {
            try {
                await fetch(`${API_URL}/btc/bottom-signals/${signalId}/clear-override`, {
                    method: 'POST',
                    headers: { 'X-API-Key': API_KEY }
                });
                loadBtcSignals();
            } catch (error) {
                console.error('Error clearing override:', error);
            }
        }
        return;
    }
    
    // Otherwise, set a manual override
    const currentStatus = signal.status || 'UNKNOWN';
    let newStatus;
    if (currentStatus === 'UNKNOWN' || currentStatus === 'NEUTRAL') {
        newStatus = 'FIRING';
    } else {
        newStatus = 'NEUTRAL';
    }
    
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals/${signalId}`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ status: newStatus })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadBtcSignals();
        }
    } catch (error) {
        console.error('Error toggling BTC signal:', error);
    }
}

async function resetBtcSignals() {
    if (!confirm('Reset all signals to UNKNOWN and clear all manual overrides?')) return;
    
    try {
        await fetch(`${API_URL}/btc/bottom-signals/reset`, { method: 'POST', headers: { 'X-API-Key': API_KEY } });
        // After reset, refresh to get fresh data from APIs
        await refreshBtcSignals();
    } catch (error) {
        console.error('Error resetting BTC signals:', error);
    }
}

// BTC session helper functions
function getEasternTimeParts() {
    try {
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            weekday: 'short'
        });
        const parts = formatter.formatToParts(new Date());
        const partMap = {};
        parts.forEach(part => {
            partMap[part.type] = part.value;
        });
        return {
            hour: Number(partMap.hour),
            minute: Number(partMap.minute),
            weekday: partMap.weekday
        };
    } catch (e) {
        console.warn('Unable to resolve Eastern time:', e);
        return null;
    }
}

function resolveActiveSession(currentSession, sessions) {
    if (currentSession && currentSession.active) return currentSession;
    return findActiveSessionClient(sessions) || currentSession;
}

function findActiveSessionClient(sessions) {
    if (!sessions) return null;
    const time = getEasternTimeParts();
    if (!time) return null;
    const { hour, minute, weekday } = time;

    if (hour >= 20 && hour < 21) {
        return { ...(sessions.asia_handoff || { name: 'Asia Handoff + Funding Reset' }), active: true };
    }
    if (hour >= 4 && hour < 6) {
        return { ...(sessions.london_open || { name: 'London Cash FX Open' }), active: true };
    }
    if (hour >= 11 && hour < 13) {
        return { ...(sessions.peak_volume || { name: 'Peak Global Volume' }), active: true };
    }
    if (hour >= 15 && hour < 16) {
        return { ...(sessions.etf_fixing || { name: 'ETF Fixing Window' }), active: true };
    }
    if (weekday === 'Fri' && hour === 15 && minute >= 55) {
        return { ...(sessions.friday_close || { name: 'Friday CME Close' }), active: true };
    }
    return null;
}

function parseNyStartTime(nyTime) {
    if (!nyTime) return null;
    let cleaned = nyTime.toLowerCase().trim();
    cleaned = cleaned.replace(/^\w{3}\s+/, ''); // remove "Fri " prefix
    const start = cleaned.split('-')[0]?.trim();
    if (!start) return null;
    const match = start.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)/i);
    if (!match) return null;
    let hour = parseInt(match[1], 10);
    const minute = match[2] ? parseInt(match[2], 10) : 0;
    const meridian = match[3].toLowerCase();
    if (meridian === 'pm' && hour !== 12) hour += 12;
    if (meridian === 'am' && hour === 12) hour = 0;
    return hour * 60 + minute;
}

function getNextSessionBySchedule(sessions) {
    if (!sessions) return null;
    const time = getEasternTimeParts();
    if (!time) return null;
    const nowMinutes = (time.hour * 60) + time.minute;
    const isFriday = time.weekday === 'Fri';

    const sessionList = Object.values(sessions)
        .map(session => {
            const startMinutes = parseNyStartTime(session.ny_time);
            if (startMinutes === null) return null;
            const isFridayOnly = (session.ny_time || '').toLowerCase().startsWith('fri');
            if (isFridayOnly && !isFriday) return null;
            return { ...session, startMinutes };
        })
        .filter(Boolean)
        .sort((a, b) => a.startMinutes - b.startMinutes);

    if (sessionList.length === 0) return null;
    const upcoming = sessionList.find(session => session.startMinutes > nowMinutes);
    return upcoming || sessionList[0];
}

function updateCryptoSessionStatus(currentSession, sessions) {
    const statusEl = document.getElementById('cryptoSessionStatus');
    if (!statusEl) return;

    if (currentSession && currentSession.active) {
        const utcTime = currentSession.utc_time || '';
        const localTime = utcTime ? formatUtcRangeToDenver(utcTime) : '';
        statusEl.innerHTML = `
            <span class="session-pill">NOW: ${currentSession.name}${localTime ? `  ${localTime}` : ''}</span>
        `;
    } else {
        const nextSession = getNextSessionBySchedule(sessions);
        statusEl.innerHTML = `
            <span class="session-pill">No active BTC session${nextSession ? `  Next: ${nextSession.name}` : ''}</span>
        `;
    }
}

function formatUtcRangeToDenver(utcRange) {
    if (!utcRange) return '--';
    let range = utcRange.trim();
    let dayPrefix = null;
    const dayMatch = range.match(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+/);
    if (dayMatch) {
        dayPrefix = dayMatch[1];
        range = range.slice(dayMatch[0].length);
    }

    const [startStr, endStr] = range.split('-');
    if (!startStr || !endStr) return utcRange;

    const parseTime = (timeStr) => {
        const match = timeStr.trim().match(/^([01]?\d|2[0-3]):([0-5]\d)$/);
        if (!match) {
            return null;
        }
        return { hours: Number(match[1]), minutes: Number(match[2]) };
    };

    const getBaseDate = () => {
        const now = new Date();
        const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
        if (!dayPrefix) return base;
        const dayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
        const targetDay = dayMap[dayPrefix];
        const offset = (targetDay - base.getUTCDay() + 7) % 7;
        base.setUTCDate(base.getUTCDate() + offset);
        return base;
    };

    const baseDate = getBaseDate();
    const startTime = parseTime(startStr);
    const endTime = parseTime(endStr);
    if (!startTime || !endTime) return utcRange;

    const startDate = new Date(Date.UTC(
        baseDate.getUTCFullYear(),
        baseDate.getUTCMonth(),
        baseDate.getUTCDate(),
        startTime.hours,
        startTime.minutes
    ));
    const endDate = new Date(Date.UTC(
        baseDate.getUTCFullYear(),
        baseDate.getUTCMonth(),
        baseDate.getUTCDate(),
        endTime.hours,
        endTime.minutes
    ));
    if (endDate <= startDate) {
        endDate.setUTCDate(endDate.getUTCDate() + 1);
    }

    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Denver',
        hour: 'numeric',
        minute: '2-digit'
    });

    return `${formatter.format(startDate)}-${formatter.format(endDate)} MT`;
}


// ==========================================
// OPTIONS FLOW (Compact — in Headlines card)
// ==========================================

let flowHotTickers = [];
let flowRecentAlerts = [];

function initOptionsFlow() {
    // Set up headlines card tab switching (SECTORS / FLOW / HEADLINES)
    document.querySelectorAll('.headlines-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.headlines-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.dataset.tab;
            const sectorsEl = document.getElementById('sectorsTabContent');
            const flowEl = document.getElementById('flowTabContent');
            const headlinesEl = document.getElementById('headlinesTabContent');
            if (sectorsEl) sectorsEl.style.display = target === 'sectors' ? '' : 'none';
            if (flowEl) flowEl.style.display = target === 'flow' ? '' : 'none';
            if (headlinesEl) headlinesEl.style.display = target === 'headlines' ? '' : 'none';
        });
    });

    loadFlowData();
    loadSectorHeatmap();
    setInterval(loadSectorHeatmap, 5 * 60 * 1000);
}

async function loadSectorHeatmap() {
    try {
        const response = await fetch(`${API_URL}/sectors/heatmap`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSectorHeatmap(data.sectors, data.spy_change_1d);
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
    }
}

function renderSectorHeatmap(sectors, spyChange) {
    const container = document.getElementById('sectorHeatmap');
    if (!container) return;
    if (!sectors || sectors.length === 0) {
        container.innerHTML = '<p class="empty-state">No sector data</p>';
        return;
    }

    // Sort by weight descending
    const sorted = [...sectors].sort((a, b) => b.weight - a.weight);

    // 3-row layout: row 1 = top 3 (Tech, Financials, Health), row 2 = next 4, row 3 = last 4
    const rows = [
        sorted.slice(0, 3),
        sorted.slice(3, 7),
        sorted.slice(7)
    ];

    // Row heights proportional to combined weight
    const rowWeights = rows.map(r => r.reduce((s, c) => s + c.weight, 0));
    const totalWeight = rowWeights.reduce((s, w) => s + w, 0);

    const maxWeight = sorted[0].weight;
    let html = '';
    rows.forEach((row, ri) => {
        const rowFlex = (rowWeights[ri] / totalWeight).toFixed(4);
        const rowTotal = row.reduce((s, c) => s + c.weight, 0);
        const cellsHtml = row.map(sector => {
            const cellFlex = (sector.weight / rowTotal).toFixed(4);
            // Scale text: 0.55–1.0 range based on weight relative to largest sector
            const scale = (0.55 + 0.45 * (sector.weight / maxWeight)).toFixed(3);
            const hm = getHeatmapStyle(sector.change_1d);
            const changeSign = sector.change_1d >= 0 ? '+' : '';
            const changeVal = sector.change_1d != null ? sector.change_1d.toFixed(2) : '0.00';
            const trend = sector.trend || 'flat';
            const trendArrow = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '→';
            const trendClass = trend === 'up' ? 'trend-up' : trend === 'down' ? 'trend-down' : 'trend-flat';
            return `<div class="sector-heatmap-cell"
                style="flex:${cellFlex};--s:${scale};border-color:${hm.borderColor};box-shadow:${hm.glow};"
                data-etf="${sector.etf}"
                title="${escapeHtml(sector.name)} (${sector.etf})\nDaily: ${changeSign}${changeVal}%\nWeekly: ${(sector.change_1w || 0) >= 0 ? '+' : ''}${(sector.change_1w || 0).toFixed(2)}%\nWeekly Trend: ${trend}\nSPY Weight: ${(sector.weight * 100).toFixed(1)}%">
                <span class="sector-hm-name">${escapeHtml(sector.name)}</span>
                <span class="sector-hm-etf">${sector.etf}</span>
                <span class="sector-hm-change" style="color:${hm.changeColor}">${changeSign}${changeVal}% <span class="sector-hm-trend ${trendClass}">${trendArrow}</span></span>
            </div>`;
        }).join('');

        html += `<div class="sector-heatmap-row" style="flex:${rowFlex};">${cellsHtml}</div>`;
    });

    container.innerHTML = html;

    // Click handler: change chart to sector ETF
    container.querySelectorAll('.sector-heatmap-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            const etf = cell.dataset.etf;
            if (etf) changeChartSymbol(etf);
        });
    });
}

function getHeatmapStyle(changePct) {
    // Returns { borderColor, glowColor, changeColor } matching bias card aesthetic.
    // Intensity scales with magnitude — stronger moves = brighter border + stronger glow.
    const abs = Math.abs(changePct || 0);
    if (abs < 0.10) {
        // Neutral — default border, no glow
        return { borderColor: 'rgba(255,255,255,0.1)', glow: 'none', changeColor: 'var(--text-secondary)' };
    }
    // Intensity: 0.3–1.0 range scaled by magnitude (caps at 2%)
    const intensity = Math.min(1.0, 0.3 + 0.7 * (abs / 2.0));
    if (changePct > 0) {
        // Bullish — green family (matches .bias-card.bullish → --accent-lime #7CFF6B)
        return {
            borderColor: `rgba(124, 255, 107, ${(0.4 + 0.6 * intensity).toFixed(2)})`,
            glow: `0 0 ${(6 + 8 * intensity).toFixed(0)}px rgba(124, 255, 107, ${(0.08 + 0.17 * intensity).toFixed(2)})`,
            changeColor: '#7CFF6B',
        };
    }
    // Bearish — orange family (matches .bias-card.bearish → --accent-orange #FF6B35)
    return {
        borderColor: `rgba(255, 107, 53, ${(0.4 + 0.6 * intensity).toFixed(2)})`,
        glow: `0 0 ${(6 + 8 * intensity).toFixed(0)}px rgba(255, 107, 53, ${(0.08 + 0.17 * intensity).toFixed(2)})`,
        changeColor: '#FF6B35',
    };
}

async function loadFlowData() {
    await loadFlowSummary();
    setInterval(loadFlowSummary, 2 * 60 * 1000);
}

async function loadFlowSummary() {
    try {
        const response = await fetch(`${API_URL}/flow/summary`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderFlowSummary(data);
    } catch (error) {
        console.error('Flow summary load failed:', error);
        const container = document.getElementById('flowCompactList');
        if (container) container.innerHTML = '<p class="empty-state">Flow data unavailable</p>';
    }
}

function renderFlowSummary(data) {
    const container = document.getElementById('flowCompactList');
    if (!container) return;
    const sentiment = data.sentiment || {};
    const hotTickers = data.hot_tickers || [];
    const recentSignals = data.recent_signals || [];
    const pcRatio = sentiment.pc_ratio || 0;
    const biasLabel = sentiment.bias || 'NEUTRAL';
    const biasColor = biasLabel === 'BULLISH' ? '#00e676'
                    : biasLabel === 'BEARISH' ? '#e5370e' : '#78909c';
    const gaugePct = Math.max(5, Math.min(95, (1 - Math.min(pcRatio, 2) / 2) * 100));
    const formatPremium = (val) => {
        if (!val) return '$0';
        if (val >= 1000000) return '$' + (val / 1000000).toFixed(1) + 'M';
        if (val >= 1000) return '$' + (val / 1000).toFixed(0) + 'K';
        return '$' + val;
    };
    const hotHtml = hotTickers.length > 0
        ? hotTickers.map(t => {
            const dirClass = (t.direction || '').toLowerCase();
            const arrow = t.direction === 'BULLISH' ? '▲' : t.direction === 'BEARISH' ? '▼' : '→';
            return `<div class="flow-hot-chip ${dirClass}" data-ticker="${escapeHtml(t.ticker)}">
                <span class="flow-hot-ticker">${escapeHtml(t.ticker)}</span>
                <span class="flow-hot-premium">${formatPremium(t.total_premium)}</span>
                <span class="flow-hot-arrow">${arrow}</span>
            </div>`;
        }).join('')
        : '<span class="flow-empty-note">No unusual activity</span>';
    const signalsHtml = recentSignals.length > 0
        ? recentSignals.map(s => {
            const dirClass = (s.direction || '').toLowerCase();
            const ago = getTimeAgo(new Date(s.created_at));
            return `<div class="flow-signal-mini ${dirClass}">
                <span class="flow-signal-ticker">${escapeHtml(s.ticker)}</span>
                <span class="flow-signal-premium">${formatPremium(s.total_premium)}</span>
                <span class="flow-signal-score">${s.score}</span>
                <span class="flow-signal-time">${ago}</span>
            </div>`;
        }).join('')
        : '<span class="flow-empty-note">No flow signals (4h)</span>';
    container.innerHTML = `
        <div class="flow-sentiment-gauge">
            <div class="flow-gauge-label">Smart Money Sentiment</div>
            <div class="flow-gauge-bar">
                <div class="flow-gauge-fill" style="width:${gaugePct}%;background:${biasColor};"></div>
            </div>
            <div class="flow-gauge-meta">
                <span>P/C: ${pcRatio.toFixed(2)}</span>
                <span style="color:${biasColor};font-weight:600;">${biasLabel}</span>
                <span>Calls: ${formatPremium(sentiment.call_premium_total)} | Puts: ${formatPremium(sentiment.put_premium_total)}</span>
            </div>
        </div>
        <div class="flow-hot-section">
            <div class="flow-section-label">Hottest Tickers</div>
            <div class="flow-hot-chips">${hotHtml}</div>
        </div>
        <div class="flow-signals-section">
            <div class="flow-section-label">Recent Flow Signals</div>
            <div class="flow-signal-list">${signalsHtml}</div>
        </div>
    `;
    container.querySelectorAll('.flow-hot-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const ticker = chip.dataset.ticker;
            if (ticker) changeChartSymbol(ticker);
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initOptionsFlow, 1100);
});




// ==========================================
// POSITION MANAGEMENT
// ==========================================

let openPositions = [];
let pendingPositionSignal = null;
let pendingPositionCard = null;
let closingPosition = null;
let currentPrices = {};  // Cache of current prices for P&L calculation
let priceUpdateInterval = null;
let currentTradeType = 'equity';  // 'equity' or 'options'
let activePositionsAccount = 'ALL';  // 'ALL', 'ROBINHOOD', 'FIDELITY', 'FIDELITY_ROTH', 'FIDELITY_401A'

function matchesAccountFilter(posAccount, filterAccount) {
    const pa = (posAccount || 'ROBINHOOD').toUpperCase();
    if (filterAccount === 'ALL') return true;
    if (filterAccount === 'FIDELITY') return pa.startsWith('FIDELITY');
    return pa === filterAccount;
}

function getSelectedAccount() {
    const active = document.querySelector('#accountToggle .trade-type-btn.active');
    return active ? active.dataset.account : 'ROBINHOOD';
}

function initPositionModals() {
    // Entry modal
    const closeEntryBtn = document.getElementById('closePositionModalBtn');
    const cancelEntryBtn = document.getElementById('cancelPositionBtn');
    const confirmEntryBtn = document.getElementById('confirmPositionBtn');
    const entryModal = document.getElementById('positionEntryModal');
    
    if (closeEntryBtn) closeEntryBtn.addEventListener('click', closePositionEntryModal);
    if (cancelEntryBtn) cancelEntryBtn.addEventListener('click', closePositionEntryModal);
    if (confirmEntryBtn) confirmEntryBtn.addEventListener('click', confirmPositionEntry);
    if (entryModal) {
        entryModal.addEventListener('click', (e) => {
            if (e.target === entryModal) closePositionEntryModal();
        });
    }
    
    // Entry price/qty inputs for live summary update
    const entryPriceInput = document.getElementById('positionEntryPrice');
    const qtyInput = document.getElementById('positionQuantity');
    if (entryPriceInput) entryPriceInput.addEventListener('input', updatePositionSummary);
    if (qtyInput) qtyInput.addEventListener('input', updatePositionSummary);
    
    // Trade type toggle (Equity / Options)
    const tradeTypeEquity = document.getElementById('tradeTypeEquity');
    const tradeTypeOptions = document.getElementById('tradeTypeOptions');
    if (tradeTypeEquity) tradeTypeEquity.addEventListener('click', () => setTradeType('equity'));
    if (tradeTypeOptions) tradeTypeOptions.addEventListener('click', () => setTradeType('options'));
    
    // Options fields - live summary update
    const optPremium = document.getElementById('optPositionPremium');
    const optContracts = document.getElementById('optPositionContracts');
    const optMaxLoss = document.getElementById('optPositionMaxLoss');
    const optStrategy = document.getElementById('optPositionStrategy');
    if (optPremium) optPremium.addEventListener('input', updateOptionsSummary);
    if (optContracts) optContracts.addEventListener('input', updateOptionsSummary);
    if (optMaxLoss) optMaxLoss.addEventListener('input', updateOptionsSummary);
    if (optStrategy) optStrategy.addEventListener('change', updateOptionsSummary);
    
    // Add leg button
    const addLegBtn = document.getElementById('optPositionAddLeg');
    if (addLegBtn) addLegBtn.addEventListener('click', addOptionsLeg);
    
    // Close modal
    const closeCloseBtn = document.getElementById('closeCloseModalBtn');
    const cancelCloseBtn = document.getElementById('cancelCloseBtn');
    const confirmCloseBtn = document.getElementById('confirmCloseBtn');
    const closeModal = document.getElementById('positionCloseModal');
    
    if (closeCloseBtn) closeCloseBtn.addEventListener('click', closePositionCloseModal);
    if (cancelCloseBtn) cancelCloseBtn.addEventListener('click', closePositionCloseModal);
    if (confirmCloseBtn) confirmCloseBtn.addEventListener('click', confirmPositionClose);
    if (closeModal) {
        closeModal.addEventListener('click', (e) => {
            if (e.target === closeModal) closePositionCloseModal();
        });
    }
    
    // Exit price/qty inputs for live P&L update
    const exitPriceInput = document.getElementById('positionExitPrice');
    const closeQtyInput = document.getElementById('closeQuantity');
    if (exitPriceInput) exitPriceInput.addEventListener('input', updateCloseSummary);
    if (closeQtyInput) closeQtyInput.addEventListener('input', updateCloseSummary);
    
    // Load existing positions, then trigger MTM for live option prices
    loadOpenPositionsEnhanced();
    triggerMarkToMarket().then(() => loadOpenPositionsEnhanced());

    // Start price updates for P&L
    startPriceUpdates();

    // Account tabs (All / RH / Fidelity)
    document.querySelectorAll('.positions-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.positions-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activePositionsAccount = btn.dataset.account;
            renderPositionsEnhanced();
            updatePositionsCount();
            loadPortfolioSummary();
        });
    });

    // Account toggle in signal acceptance modal
    document.querySelectorAll('#accountToggle .trade-type-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#accountToggle .trade-type-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

function openPositionEntryModal(signal, card) {
    pendingPositionSignal = signal;
    pendingPositionCard = card;
    
    // Populate modal
    document.getElementById('positionTickerDisplay').textContent = signal.ticker;
    const dirDisplay = document.getElementById('positionDirectionDisplay');
    dirDisplay.textContent = signal.direction;
    dirDisplay.className = 'position-direction-display ' + signal.direction;
    
    // Set label based on asset class
    const qtyLabel = document.getElementById('positionQtyLabel');
    if (signal.asset_class === 'CRYPTO') {
        qtyLabel.textContent = 'Quantity (Tokens) *';
    } else {
        qtyLabel.textContent = 'Quantity (Shares) *';
    }
    
    // Pre-fill entry price from signal
    document.getElementById('positionEntryPrice').value = signal.entry_price?.toFixed(2) || '';
    document.getElementById('positionQuantity').value = '';
    
    // Update summary
    document.getElementById('summaryStop').textContent = '$' + (signal.stop_loss?.toFixed(2) || '--');
    document.getElementById('summaryTarget').textContent = '$' + (signal.target_1?.toFixed(2) || '--');
    document.getElementById('summarySize').textContent = '$--';
    document.getElementById('summaryRisk').textContent = '$--';
    
    // Reset to equity mode
    setTradeType('equity');
    
    // Pre-fill options direction based on signal direction
    const optDirection = signal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    
    // Pre-fill options strategy suggestion based on direction
    const optStrategySelect = document.getElementById('optPositionStrategy');
    if (optStrategySelect) {
        optStrategySelect.value = signal.direction === 'LONG' ? 'LONG_CALL' : 'LONG_PUT';
    }
    
    // Reset options fields
    resetOptionsFields();
    
    // Pre-fill first leg type based on direction
    const firstLegType = document.querySelector('#optPositionLegs .opt-leg-type');
    if (firstLegType) {
        firstLegType.value = signal.direction === 'LONG' ? 'CALL' : 'PUT';
    }
    
    // Set default expiry to ~30 days out
    const firstLegExpiry = document.querySelector('#optPositionLegs .opt-leg-expiry');
    if (firstLegExpiry) {
        const defaultExpiry = new Date();
        defaultExpiry.setDate(defaultExpiry.getDate() + 30);
        firstLegExpiry.value = defaultExpiry.toISOString().split('T')[0];
    }
    
    // Pre-fill strike near entry price (round to nearest 0.5)
    const firstLegStrike = document.querySelector('#optPositionLegs .opt-leg-strike');
    if (firstLegStrike && signal.entry_price) {
        firstLegStrike.value = (Math.round(signal.entry_price * 2) / 2).toFixed(1);
    }
    
    // Show modal
    document.getElementById('positionEntryModal').classList.add('active');
}

function closePositionEntryModal() {
    document.getElementById('positionEntryModal').classList.remove('active');
    pendingPositionSignal = null;
    pendingPositionCard = null;
    currentTradeType = 'equity';
}

function updatePositionSummary() {
    if (!pendingPositionSignal) return;
    
    const entryPrice = parseFloat(document.getElementById('positionEntryPrice').value) || 0;
    const qty = parseFloat(document.getElementById('positionQuantity').value) || 0;
    const stopLoss = pendingPositionSignal.stop_loss || 0;
    
    const positionSize = entryPrice * qty;
    const riskPerShare = Math.abs(entryPrice - stopLoss);
    const totalRisk = riskPerShare * qty;
    
    document.getElementById('summarySize').textContent = '$' + positionSize.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('summaryRisk').textContent = '$' + totalRisk.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

async function confirmPositionEntry() {
    if (!pendingPositionSignal) return;

    if (currentTradeType === 'options') {
        await confirmOptionsPositionEntry();
        return;
    }

    // Save signal reference before modal close nulls it
    const signal = pendingPositionSignal;
    const card = pendingPositionCard;

    const entryPrice = parseFloat(document.getElementById('positionEntryPrice').value);
    const qty = parseFloat(document.getElementById('positionQuantity').value);

    if (!entryPrice || !qty) {
        alert('Please enter both entry price and quantity');
        return;
    }

    try {
        // Accept signal via new API endpoint (includes full logging)
        const response = await fetch(`${API_URL}/signals/${signal.signal_id}/accept`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                signal_id: signal.signal_id,
                actual_entry_price: entryPrice,
                quantity: qty,
                stop_loss: signal.stop_loss,
                target_1: signal.target_1,
                target_2: signal.target_2,
                account: getSelectedAccount(),
                notes: `Accepted via Trade Ideas UI`
            })
        });

        const data = await response.json();

        if (data.status === 'accepted' || data.position_id) {
            // Remove signal card with animation
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                setTimeout(() => {
                    card.remove();
                    // Auto-refill Trade Ideas list
                    refillTradeIdeas();
                }, 300);
            }

            // Close modal
            closePositionEntryModal();

            // Reload positions
            await loadOpenPositionsEnhanced();

            // Add ticker to chart tabs
            addPositionChartTab(signal.ticker);

            // Store price levels for chart display
            storePriceLevels(signal.ticker, {
                entry: entryPrice,
                stop: signal.stop_loss,
                target1: signal.target_1,
                target2: signal.target_2
            });

            console.log(`Position accepted: ${signal.ticker} ${signal.direction} @ $${entryPrice}`);
        } else {
            alert('Failed to accept signal: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error accepting signal:', error);
        alert('Failed to accept signal');
    }
}

// ==========================================
// TRADE TYPE TOGGLE (Equity / Options)
// ==========================================

function setTradeType(type) {
    currentTradeType = type;
    const equityBtn = document.getElementById('tradeTypeEquity');
    const optionsBtn = document.getElementById('tradeTypeOptions');
    const equityFields = document.getElementById('equityFields');
    const optionsFields = document.getElementById('optionsFields');
    const modalContainer = document.getElementById('positionModalContainer');
    const modalTitle = document.getElementById('positionModalTitle');
    const confirmBtn = document.getElementById('confirmPositionBtn');
    
    if (type === 'equity') {
        equityBtn.classList.add('active');
        optionsBtn.classList.remove('active');
        equityFields.style.display = 'block';
        optionsFields.style.display = 'none';
        modalContainer.classList.remove('options-mode');
        modalTitle.textContent = 'Open Position';
        confirmBtn.textContent = 'Open Position';
    } else {
        equityBtn.classList.remove('active');
        optionsBtn.classList.add('active');
        equityFields.style.display = 'none';
        optionsFields.style.display = 'block';
        modalContainer.classList.add('options-mode');
        modalTitle.textContent = 'Open Options Position';
        confirmBtn.textContent = 'Open Options Position';
        updateOptionsSummary();
    }
}

function resetOptionsFields() {
    // Reset strategy
    const strategySelect = document.getElementById('optPositionStrategy');
    if (strategySelect) strategySelect.selectedIndex = 0;
    
    // Clear numeric inputs
    const fieldsToReset = ['optPositionPremium', 'optPositionMaxProfit', 'optPositionMaxLoss', 'optPositionBreakeven', 'optPositionThesis'];
    fieldsToReset.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    
    // Reset contracts to 1
    const contracts = document.getElementById('optPositionContracts');
    if (contracts) contracts.value = '1';
    
    // Reset legs to single default leg
    const legsContainer = document.getElementById('optPositionLegs');
    if (legsContainer) {
        legsContainer.innerHTML = `
            <div class="opt-leg-row" data-leg="1">
                <div class="opt-leg-fields">
                    <select class="opt-leg-action position-input-sm">
                        <option value="BUY">BUY</option>
                        <option value="SELL">SELL</option>
                    </select>
                    <select class="opt-leg-type position-input-sm">
                        <option value="CALL">CALL</option>
                        <option value="PUT">PUT</option>
                    </select>
                    <input type="number" class="opt-leg-strike position-input-sm" placeholder="Strike" step="0.5">
                    <input type="date" class="opt-leg-expiry position-input-sm">
                    <input type="number" class="opt-leg-qty position-input-sm" placeholder="Qty" value="1" min="1" step="1">
                    <input type="number" class="opt-leg-premium position-input-sm" placeholder="Premium" step="0.01">
                </div>
            </div>
        `;
    }
}

function addOptionsLeg() {
    const legsContainer = document.getElementById('optPositionLegs');
    if (!legsContainer) return;
    
    const legCount = legsContainer.querySelectorAll('.opt-leg-row').length + 1;
    
    const legHTML = `
        <div class="opt-leg-row" data-leg="${legCount}">
            <div class="opt-leg-fields">
                <select class="opt-leg-action position-input-sm">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                </select>
                <select class="opt-leg-type position-input-sm">
                    <option value="CALL">CALL</option>
                    <option value="PUT">PUT</option>
                </select>
                <input type="number" class="opt-leg-strike position-input-sm" placeholder="Strike" step="0.5">
                <input type="date" class="opt-leg-expiry position-input-sm">
                <input type="number" class="opt-leg-qty position-input-sm" placeholder="Qty" value="1" min="1" step="1">
                <input type="number" class="opt-leg-premium position-input-sm" placeholder="Premium" step="0.01">
            </div>
        </div>
    `;
    
    legsContainer.insertAdjacentHTML('beforeend', legHTML);
}

function collectOptionsLegs() {
    const legRows = document.querySelectorAll('#optPositionLegs .opt-leg-row');
    const legs = [];
    
    legRows.forEach(row => {
        const action = row.querySelector('.opt-leg-action')?.value;
        const optionType = row.querySelector('.opt-leg-type')?.value;
        const strike = parseFloat(row.querySelector('.opt-leg-strike')?.value);
        const expiry = row.querySelector('.opt-leg-expiry')?.value;
        const qty = parseInt(row.querySelector('.opt-leg-qty')?.value) || 1;
        const premium = parseFloat(row.querySelector('.opt-leg-premium')?.value);
        
        if (strike && expiry) {
            legs.push({
                action: action,
                option_type: optionType,
                strike: strike,
                expiration: expiry,
                quantity: qty,
                premium: premium || 0
            });
        }
    });
    
    return legs;
}

function updateOptionsSummary() {
    if (!pendingPositionSignal) return;
    
    const strategy = document.getElementById('optPositionStrategy')?.value || '--';
    const premium = parseFloat(document.getElementById('optPositionPremium')?.value) || 0;
    const contracts = parseInt(document.getElementById('optPositionContracts')?.value) || 1;
    const maxLoss = parseFloat(document.getElementById('optPositionMaxLoss')?.value);
    
    // Strategy display name
    const strategyNames = {
        'LONG_CALL': 'Long Call', 'LONG_PUT': 'Long Put',
        'BULL_CALL_SPREAD': 'Bull Call Spread', 'BEAR_PUT_SPREAD': 'Bear Put Spread',
        'BULL_PUT_SPREAD': 'Bull Put Spread', 'BEAR_CALL_SPREAD': 'Bear Call Spread',
        'IRON_CONDOR': 'Iron Condor', 'STRADDLE': 'Straddle',
        'STRANGLE': 'Strangle', 'CUSTOM': 'Custom'
    };
    
    // Direction from signal
    const direction = pendingPositionSignal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    
    document.getElementById('optSummaryStrategy').textContent = strategyNames[strategy] || strategy;
    document.getElementById('optSummaryDirection').textContent = direction;
    
    // Net premium display (premium is always positive = what you paid)
    const absPremium = Math.abs(premium);
    const totalPremium = absPremium * contracts;
    const premiumStr = totalPremium !== 0 ? '$' + totalPremium.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '$--';
    document.getElementById('optSummaryPremium').textContent = premiumStr;

    // Max risk — default to premium paid if not specified
    if (maxLoss) {
        document.getElementById('optSummaryRisk').textContent = '$' + Math.abs(maxLoss).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } else if (absPremium > 0) {
        document.getElementById('optSummaryRisk').textContent = '$' + totalPremium.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } else {
        document.getElementById('optSummaryRisk').textContent = '$--';
    }
}

async function confirmOptionsPositionEntry() {
    if (!pendingPositionSignal) return;
    
    const strategy = document.getElementById('optPositionStrategy')?.value;
    const premium = parseFloat(document.getElementById('optPositionPremium')?.value);
    const contracts = parseInt(document.getElementById('optPositionContracts')?.value) || 1;
    const legs = collectOptionsLegs();
    
    // Validate required fields
    if (!strategy) {
        alert('Please select an options strategy');
        return;
    }
    if (isNaN(premium)) {
        alert('Please enter the net premium');
        return;
    }
    if (legs.length === 0) {
        alert('Please fill in at least one option leg (strike and expiry required)');
        return;
    }
    
    const direction = pendingPositionSignal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    const maxProfit = parseFloat(document.getElementById('optPositionMaxProfit')?.value) || null;
    const maxLoss = parseFloat(document.getElementById('optPositionMaxLoss')?.value) || null;
    const breakevenStr = document.getElementById('optPositionBreakeven')?.value || '';
    const breakeven = breakevenStr ? breakevenStr.split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n)) : null;
    const thesis = document.getElementById('optPositionThesis')?.value || '';
    
    try {
        // Step 1: Create options position
        const optResponse = await fetch(`${API_URL}/signals/${pendingPositionSignal.signal_id}/accept-options`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                signal_id: pendingPositionSignal.signal_id,
                underlying: pendingPositionSignal.ticker,
                strategy_type: strategy,
                direction: direction,
                legs: legs,
                net_premium: Math.abs(premium),
                contracts: contracts,
                max_profit: maxProfit,
                max_loss: maxLoss,
                breakeven: breakeven,
                thesis: thesis,
                account: getSelectedAccount(),
                notes: `Accepted via Trade Ideas UI (Options: ${strategy})`
            })
        });
        
        const data = await optResponse.json();
        
        if (data.status === 'success' || data.status === 'accepted' || data.position_id) {
            // Remove signal card with animation
            if (pendingPositionCard) {
                pendingPositionCard.style.opacity = '0';
                pendingPositionCard.style.transform = 'translateX(-20px)';
                setTimeout(() => {
                    pendingPositionCard.remove();
                    refillTradeIdeas();
                }, 300);
            }
            
            // Close modal
            closePositionEntryModal();
            
            // Reload positions (both equity and options)
            await loadOpenPositionsEnhanced();
            
            // Add ticker to chart tabs
            addPositionChartTab(pendingPositionSignal.ticker);
            
            console.log(`ðŸ“Š Options position accepted: ${pendingPositionSignal.ticker} ${strategy} - Premium: $${premium}`);
        } else {
            alert('Failed to accept signal as options: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error accepting signal as options:', error);
        alert('Failed to accept signal as options position');
    }
}

// Store price levels for chart sidebar display
function storePriceLevels(ticker, levels) {
    if (!window.activePriceLevels) {
        window.activePriceLevels = {};
    }
    window.activePriceLevels[ticker] = levels;
    
    // Update panel if currently viewing this ticker
    if (currentSymbol === ticker) {
        updatePriceLevelsPanel(ticker);
    }
}

async function loadOpenPositionsEnhanced() {
    try {
        const response = await fetch(`${API_URL}/v2/positions?status=OPEN`);
        const data = await response.json();

        if (data.positions) {
            openPositions = data.positions;
            renderPositionsEnhanced();
            updatePositionsCount();
            updatePositionChartTabs();
            loadPortfolioSummary();
        }
    } catch (error) {
        console.error('Error loading positions:', error);
    }
}

async function loadPortfolioSummary() {
    try {
        // Fetch RH and Fidelity Roth summaries separately so each section gets its own data
        const [rhRes, fidRothRes] = await Promise.all([
            fetch(`${API_URL}/v2/positions/summary?account=ROBINHOOD`),
            fetch(`${API_URL}/v2/positions/summary?account=FIDELITY_ROTH`),
        ]);
        const rhData = await rhRes.json();
        const fidRothData = await fidRothRes.json();
        renderPortfolioSummaryWidget(rhData, fidRothData);
    } catch (error) {
        console.error('Error loading portfolio summary:', error);
    }
}

// ── Headlines ────────────────────────────────────────────────────────

// Sync headlines card height to match the Market Bias composite panel
function syncHeadlinesHeight() {
    const biasPanel = document.querySelector('.bias-composite-panel');
    const headlinesCard = document.getElementById('headlinesCard');
    if (!biasPanel || !headlinesCard) return;
    const h = biasPanel.offsetHeight;
    if (h > 0) {
        headlinesCard.style.maxHeight = h + 'px';
    }
}

async function loadHeadlines() {
    try {
        const response = await fetch(`${API_URL}/market/news?limit=20`);
        const data = await response.json();
        renderHeadlines(data.articles || []);
    } catch (error) {
        console.error('Error loading headlines:', error);
        const list = document.getElementById('headlinesList');
        if (list) list.innerHTML = '<li class="headlines-empty">Headlines unavailable</li>';
    }
}

// Refresh headlines at midday (12:00 ET) and 1h before close (15:00 ET)
function startHeadlineScheduler() {
    const REFRESH_HOURS_ET = [12, 15]; // noon and 3pm Eastern
    const fired = new Set();

    setInterval(() => {
        // Get current ET time
        const nowET = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
        const h = nowET.getHours();
        const m = nowET.getMinutes();
        const day = nowET.getDay();
        // Weekdays only
        if (day === 0 || day === 6) return;
        const key = `${nowET.toDateString()}-${h}`;
        if (REFRESH_HOURS_ET.includes(h) && m < 5 && !fired.has(key)) {
            fired.add(key);
            console.log(`Headlines scheduled refresh at ${h}:00 ET`);
            loadHeadlines();
        }
        // Clean old keys at midnight
        if (h === 0 && m < 2) fired.clear();
    }, 60000); // check every minute
}

function renderHeadlines(articles) {
    const heading = document.getElementById('headlinesHeading');
    if (heading) {
        const now = new Date();
        const dayName = now.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase();
        const dateStr = now.toLocaleDateString('en-US', { month: 'long', day: 'numeric' }).toUpperCase();
        heading.textContent = `HEADLINES FOR ${dayName}, ${dateStr}`;
    }

    const list = document.getElementById('headlinesList');
    if (!list) return;

    if (!articles.length) {
        list.innerHTML = '<li class="headlines-empty">No headlines available</li>';
        return;
    }

    list.innerHTML = articles.map(a => {
        const tickers = (a.tickers || []).slice(0, 3).map(t =>
            `<span class="headline-ticker">${t}</span>`
        ).join('');

        let timeStr = '';
        if (a.published) {
            const mins = Math.round((Date.now() - new Date(a.published).getTime()) / 60000);
            timeStr = mins < 1 ? 'just now' : mins < 60 ? `${mins}m ago` : mins < 1440 ? `${Math.round(mins / 60)}h ago` : `${Math.round(mins / 1440)}d ago`;
        }

        const source = a.source ? `<span>${a.source}</span>` : '';

        return `<li>
            <a class="headline-link" href="${a.url}" target="_blank" rel="noopener">${a.title}</a>
            <div class="headline-meta">
                ${source}
                ${timeStr ? `<span>${timeStr}</span>` : ''}
                ${tickers ? `<span class="headline-tickers">${tickers}</span>` : ''}
            </div>
        </li>`;
    }).join('');
}

// Fidelity Retirement (401A + 403B) — no active trading, updated manually
const FIDELITY_RETIREMENT = 10341;     // 401A ($10,108) + 403B ($233)

function renderPortfolioSummaryWidget(rhSummary, fidRothSummary) {
    const rhBalance = rhSummary.account_balance || 0;
    const fidRothBalance = fidRothSummary.account_balance || 0;
    const combinedBalance = rhBalance + fidRothBalance + FIDELITY_RETIREMENT;

    // Combined balance (extra large)
    const combinedEl = document.getElementById('portfolioCombinedBalance');
    if (combinedEl) {
        combinedEl.textContent = '$' + combinedBalance.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    }

    // RH balance + breakdown
    const rhBalEl = document.getElementById('rhBalance');
    if (rhBalEl) {
        rhBalEl.textContent = '$' + rhBalance.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    }
    const rhBreakdown = document.getElementById('rhBreakdown');
    if (rhBreakdown && rhSummary.cash != null) {
        const cashStr = '$' + rhSummary.cash.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
        const posVal = rhSummary.position_value || 0;
        const posStr = '$' + posVal.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
        rhBreakdown.innerHTML = `<span class="rh-cash-link" title="Update cash balance">Cash ${cashStr}</span><button class="withdraw-btn" title="Log withdrawal or deposit">W/D</button><span>Positions ${posStr}</span>`;
        rhBreakdown.querySelector('.rh-cash-link').addEventListener('click', () => showCashUpdateModal(rhSummary.cash));
        rhBreakdown.querySelector('.withdraw-btn').addEventListener('click', () => showWithdrawModal());
    }
    const rhMeta = document.getElementById('rhMeta');
    if (rhMeta) {
        const parts = [];
        if (rhSummary.position_count) parts.push(rhSummary.position_count + ' pos');
        if (rhSummary.net_direction && rhSummary.net_direction !== 'FLAT') parts.push(rhSummary.net_direction);
        if (rhSummary.nearest_dte !== null && rhSummary.nearest_dte !== undefined) parts.push(rhSummary.nearest_dte + ' DTE');
        if (rhSummary.stale_positions > 0) parts.push(rhSummary.stale_positions + ' stale');
        rhMeta.textContent = parts.join(' \u00B7 ');
    }

    // Fidelity Active Trading (Roth) — now from live data
    const actEl = document.getElementById('fidelityActiveBalance');
    if (actEl) {
        actEl.textContent = '$' + fidRothBalance.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    }

    // Fidelity Retirement (static — no active trading)
    const retEl = document.getElementById('fidelityRetirementBalance');
    if (retEl) retEl.textContent = '$' + FIDELITY_RETIREMENT.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}

function showCashUpdateModal(currentCash) {
    const existing = document.getElementById('cashUpdateModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'cashUpdateModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="cash-update-modal">
            <h3>Update RH Cash Balance</h3>
            <input type="number" id="cashUpdateInput" step="0.01" value="${(currentCash || 0).toFixed(2)}" />
            <div class="cash-modal-actions">
                <button id="cashUpdateSave" class="cash-modal-btn save">Save</button>
                <button id="cashUpdateCancel" class="cash-modal-btn cancel">Cancel</button>
            </div>
        </div>`;
    document.body.appendChild(modal);

    const input = document.getElementById('cashUpdateInput');
    input.select();

    document.getElementById('cashUpdateSave').addEventListener('click', async () => {
        const val = parseFloat(input.value);
        if (isNaN(val)) return;
        try {
            const resp = await fetch(`${API_URL}/v2/positions/reconcile-cash`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({cash: val, account: 'ROBINHOOD'}),
            });
            const data = await resp.json();
            modal.remove();
            loadPortfolioSummary();
            if (data.drift && Math.abs(data.drift) > 0.01) {
                console.log(`Cash reconciled: drift was $${data.drift > 0 ? '+' : ''}${data.drift.toFixed(2)}`);
            }
        } catch (e) {
            console.error('Failed to update cash:', e);
        }
    });

    document.getElementById('cashUpdateCancel').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') document.getElementById('cashUpdateSave').click();
        if (e.key === 'Escape') modal.remove();
    });
}

function showWithdrawModal() {
    const existing = document.getElementById('withdrawModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'withdrawModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="cash-update-modal">
            <h3>Log Withdrawal / Deposit</h3>
            <div class="withdraw-type-toggle">
                <button class="withdraw-toggle active" data-type="withdraw">Withdraw</button>
                <button class="withdraw-toggle" data-type="deposit">Deposit</button>
            </div>
            <input type="number" id="withdrawAmountInput" step="0.01" placeholder="Amount" min="0" />
            <input type="text" id="withdrawNoteInput" placeholder="Note (optional)" />
            <div class="cash-modal-actions">
                <button id="withdrawSave" class="cash-modal-btn save">Log</button>
                <button id="withdrawCancel" class="cash-modal-btn cancel">Cancel</button>
            </div>
        </div>`;
    document.body.appendChild(modal);

    let flowType = 'withdraw';
    const toggles = modal.querySelectorAll('.withdraw-toggle');
    toggles.forEach(btn => btn.addEventListener('click', () => {
        toggles.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        flowType = btn.dataset.type;
    }));

    const amtInput = document.getElementById('withdrawAmountInput');
    amtInput.focus();

    document.getElementById('withdrawSave').addEventListener('click', async () => {
        const val = parseFloat(amtInput.value);
        if (isNaN(val) || val <= 0) return;
        const amount = flowType === 'withdraw' ? -val : val;
        const note = document.getElementById('withdrawNoteInput').value.trim();
        try {
            await fetch(`${API_URL}/portfolio/cash-flows`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({
                    amount: amount,
                    flow_type: 'ACH',
                    description: note || (flowType === 'withdraw' ? 'Withdrawal' : 'Deposit'),
                    account_name: 'Robinhood',
                    adjust_balance: true,
                }),
            });
            modal.remove();
            loadPortfolioSummary();
        } catch (e) {
            console.error('Failed to log cash flow:', e);
        }
    });

    document.getElementById('withdrawCancel').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    amtInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') document.getElementById('withdrawSave').click();
        if (e.key === 'Escape') modal.remove();
    });
}

function updatePositionsCount() {
    const countEl = document.getElementById('positionsCount');
    if (countEl) {
        const count = openPositions.filter(p => matchesAccountFilter(p.account, activePositionsAccount)).length;
        countEl.textContent = count;
    }
}

function renderPositionCard(pos) {
    const posId = pos.position_id || pos.id || pos.signal_id;

    // P&L display
    const pnl = pos.unrealized_pnl || 0;
    const pnlClass = pnl >= 0 ? 'positive' : 'negative';
    const pnlStr = (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2);

    // Structure badge
    const structure = pos.structure || pos.strategy || 'EQUITY';
    const structureDisplay = structure.replace(/_/g, ' ').toUpperCase();

    // Strikes + DTE line for options
    let strikeLine = '';
    if (pos.long_strike || pos.short_strike) {
        const strikes = [pos.long_strike, pos.short_strike].filter(Boolean).join('/');
        const expiryStr = pos.expiry ? new Date(pos.expiry + 'T00:00:00').toLocaleDateString('en-US', {month: 'numeric', day: 'numeric'}) : '';
        const dteStr = pos.dte !== null && pos.dte !== undefined ? `${pos.dte} DTE` : '';
        const dteBadge = pos.dte !== null && pos.dte <= 7 ? 'dte-urgent' : pos.dte <= 14 ? 'dte-soon' : '';
        strikeLine = `<div class="position-strikes">${strikes} ${expiryStr} <span class="${dteBadge}">${dteStr}</span></div>`;
    } else if (pos.expiry) {
        const expiryStr = new Date(pos.expiry + 'T00:00:00').toLocaleDateString('en-US', {month: 'numeric', day: 'numeric'});
        const dteStr = pos.dte !== null && pos.dte !== undefined ? `${pos.dte} DTE` : '';
        strikeLine = `<div class="position-strikes">${expiryStr} <span>${dteStr}</span></div>`;
    }

    // Max loss bar
    let maxLossBar = '';
    if (pos.max_loss && pos.max_loss > 0) {
        const lossConsumed = Math.min(100, Math.max(0, (Math.abs(pnl) / pos.max_loss) * 100));
        const barClass = pnl < 0 ? (lossConsumed > 75 ? 'loss-severe' : lossConsumed > 50 ? 'loss-warning' : 'loss-ok') : 'loss-ok';
        maxLossBar = `
            <div class="max-loss-bar-wrap">
                <div class="max-loss-bar ${barClass}" style="width: ${lossConsumed}%"></div>
                <span class="max-loss-label">Max loss: $${pos.max_loss.toFixed(0)}</span>
            </div>`;
    }

    // Current mark price display
    let markLine = '';
    const struct = (pos.structure || '').toLowerCase();
    const isSpread = struct.includes('spread') || struct.includes('credit') || struct.includes('debit');
    if (isSpread && pos.long_leg_price != null && pos.short_leg_price != null) {
        markLine = `
            <div class="position-mark">
                <div class="mark-legs">
                    <span class="mark-leg">Long <span class="mark-leg-price">$${pos.long_leg_price.toFixed(2)}</span></span>
                    <span class="mark-divider">/</span>
                    <span class="mark-leg">Short <span class="mark-leg-price">$${pos.short_leg_price.toFixed(2)}</span></span>
                </div>
                <div class="mark-net">Net: $${pos.current_price?.toFixed(2) || '--'}</div>
            </div>`;
    } else if (pos.current_price != null) {
        markLine = `
            <div class="position-mark">
                <span class="mark-label">Mark</span>
                <span class="mark-price">$${pos.current_price.toFixed(2)}</span>
            </div>`;
    }

    // Price freshness
    let freshness = '';
    if (pos.price_updated_at) {
        const updatedAt = new Date(pos.price_updated_at);
        const mins = Math.round((Date.now() - updatedAt.getTime()) / 60000);
        freshness = mins < 1 ? 'just now' : mins < 60 ? `${mins}m ago` : `${Math.round(mins / 60)}h ago`;
    }

    // Counter-signal warning
    let counterBanner = '';
    if (pos.counter_signal) {
        const cs = pos.counter_signal;
        let csTime = '';
        if (cs.timestamp) {
            try {
                const csDate = new Date(cs.timestamp);
                const csMin = Math.round((Date.now() - csDate.getTime()) / 60000);
                csTime = csMin < 1 ? 'just now' : csMin < 60 ? `${csMin}m ago` : `${Math.round(csMin / 60)}h ago`;
            } catch(e) {}
        }
        counterBanner = `
            <div class="counter-signal-warning">
                Counter-signal: ${cs.direction || '?'} ${formatStrategyName(cs.strategy)} (score: ${cs.score || 'N/A'})${csTime ? ` <span class="counter-signal-time">${csTime}</span>` : ''}
            </div>`;
    }

    return `
        <div class="position-card${pos.counter_signal ? ' has-counter-signal' : ''}" data-position-id="${posId}">
            <button class="position-remove-btn" data-position-id="${posId}" title="Remove position">x</button>
            <div class="position-card-header">
                <span class="position-ticker" data-ticker="${pos.ticker}">${pos.ticker}</span>
                <span class="position-structure-badge">${structureDisplay}</span>
            </div>
            ${counterBanner}
            ${strikeLine}
            <div class="position-details">
                <div class="position-detail">
                    <div class="position-detail-label">Entry</div>
                    <div class="position-detail-value">$${pos.entry_price?.toFixed(2) || '--'}</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">Qty</div>
                    <div class="position-detail-value">${pos.quantity || '--'}</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">Stop</div>
                    <div class="position-detail-value">${pos.stop_loss ? '$' + pos.stop_loss.toFixed(2) : '--'}</div>
                </div>
                <div class="position-detail">
                    <div class="position-detail-label">Target</div>
                    <div class="position-detail-value">${pos.target_1 ? '$' + pos.target_1.toFixed(2) : '--'}</div>
                </div>
            </div>
            ${maxLossBar}
            ${markLine}
            <div class="position-pnl">
                <span class="pnl-label">Unrealized P&L${freshness ? ` <span class="pnl-freshness">${freshness}</span>` : ''}</span>
                <span class="pnl-value ${pnlClass}">${pnlStr}</span>
            </div>
            <div class="position-actions">
                <button class="position-btn-small edit-btn" data-position-id="${posId}">Edit</button>
                <button class="position-btn-small close-btn" data-position-id="${posId}">Close</button>
            </div>
        </div>
    `;
}

function renderPositionsEnhanced() {
    const container = document.getElementById('openPositions');
    if (!container) return;

    // Filter by active account tab
    const filteredPositions = openPositions.filter(p => matchesAccountFilter(p.account, activePositionsAccount));

    if (!filteredPositions || filteredPositions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open positions</p>';
        return;
    }

    // Categorize positions into groups
    const optionsLong = [];
    const optionsShort = [];
    const stocks = [];

    for (const pos of filteredPositions) {
        const struct = (pos.structure || '').toLowerCase();
        const isStock = struct === 'stock' || struct === 'stock_long' || struct === 'long_stock' ||
                        struct === 'stock_short' || struct === 'short_stock' ||
                        (!struct && (pos.asset_type || '').toUpperCase() === 'EQUITY');

        if (isStock) {
            stocks.push(pos);
        } else {
            // Use direction field: LONG/BULLISH → Options (Long), SHORT/BEARISH → Options (Short)
            const dir = (pos.direction || '').toUpperCase();
            if (dir === 'SHORT' || dir === 'BEARISH') {
                optionsShort.push(pos);
            } else {
                optionsLong.push(pos);
            }
        }
    }

    // Sort each group: options by DTE (soonest first), stocks alphabetically
    const sortByDte = (a, b) => {
        const dteA = a.dte ?? 9999;
        const dteB = b.dte ?? 9999;
        if (dteA !== dteB) return dteA - dteB;
        return (a.ticker || '').localeCompare(b.ticker || '');
    };
    optionsLong.sort(sortByDte);
    optionsShort.sort(sortByDte);
    stocks.sort((a, b) => (a.ticker || '').localeCompare(b.ticker || ''));

    // Render with section dividers
    let html = '';
    if (optionsLong.length > 0) {
        html += '<div class="position-group-divider">Options (Long)</div>';
        html += optionsLong.map(renderPositionCard).join('');
    }
    if (optionsShort.length > 0) {
        html += '<div class="position-group-divider">Options (Short)</div>';
        html += optionsShort.map(renderPositionCard).join('');
    }
    if (stocks.length > 0) {
        html += '<div class="position-group-divider">Stocks</div>';
        html += stocks.map(renderPositionCard).join('');
    }
    container.innerHTML = html;
    
    // Attach events
    container.querySelectorAll('.position-ticker').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            changeChartSymbol(e.target.dataset.ticker);
        });
    });

    container.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId);
            if (position) openPositionCloseModal(position);
        });
    });

    container.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId);
            if (position) openPositionEditModal(position);
        });
    });

    container.querySelectorAll('.position-remove-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId)
            if (position) openPositionRemoveModal(position);
        });
    });
}

function calculatePnL(position, currentPrice) {
    if (!position.entry_price || !position.quantity || !currentPrice) return 0;
    
    if (position.direction === 'LONG') {
        return (currentPrice - position.entry_price) * position.quantity;
    } else {
        return (position.entry_price - currentPrice) * position.quantity;
    }
}

function openPositionCloseModal(position) {
    closingPosition = position;
    const struct = (position.structure || '').toLowerCase();
    const stockStructures = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'];
    const isStock = stockStructures.includes(struct) || (!struct && position.asset_type === 'EQUITY');
    const isOption = !isStock && (position.asset_type === 'OPTION' || position.asset_type === 'SPREAD' || (struct && !stockStructures.includes(struct)));
    const unitLabel = isOption ? 'contracts' : (position.asset_class === 'CRYPTO' ? 'tokens' : 'shares');

    document.getElementById('closeTickerDisplay').textContent = position.ticker
        + (position.structure && !isStock ? ` (${position.structure.replace(/_/g, ' ')})` : '');

    const exitInput = document.getElementById('positionExitPrice');
    exitInput.value = '';
    exitInput.placeholder = isOption ? 'e.g. 0.45' : 'e.g. 235.00';
    exitInput.step = isOption ? '0.01' : '0.01';

    // Structure-aware label for exit price
    const spreadKeywords = ['spread', 'condor', 'butterfly', 'strangle', 'straddle'];
    const isSpread = spreadKeywords.some(kw => struct.includes(kw));
    if (isSpread) {
        exitInput.previousElementSibling.textContent = 'Net Close Premium per Spread *';
    } else if (isOption) {
        exitInput.previousElementSibling.textContent = 'Exit Premium per Contract *';
    } else {
        exitInput.previousElementSibling.textContent = 'Exit Price *';
    }

    document.getElementById('closeQuantity').value = position.quantity;
    document.getElementById('closeQtyLabel').textContent = isOption ? 'Contracts to Close *' : 'Quantity to Close *';
    document.getElementById('closeQtyHint').textContent = `You have ${position.quantity} ${unitLabel}`;
    const entryUnit = isSpread ? '/spread' : (isOption ? '/contract' : '');
    document.getElementById('closeEntryPrice').textContent = '$' + (position.entry_price?.toFixed(2) || '--') + entryUnit;
    document.getElementById('closeRealizedPnL').textContent = '$--';
    document.getElementById('closeRealizedPnL').className = '';

    document.getElementById('positionCloseModal').classList.add('active');
}

function closePositionCloseModal() {
    document.getElementById('positionCloseModal').classList.remove('active');
    closingPosition = null;
}

function openPositionRemoveModal(position) {
    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal remove-modal">
            <div class="modal-header">
                <h3>Remove ${position.ticker} Position</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <p class="warning-text">THIS TRADE WILL NOT BE ARCHIVED FOR BACKTESTING</p>
                <p>Use this only for glitched positions or trades you do not want logged.</p>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn remove-position">Remove Position</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.remove-position').addEventListener('click', async () => {
        modal.remove();
        await removePositionWithoutArchive(position);
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function removePositionWithoutArchive(position) {
    try {
        const posId = position.position_id || position.id;
        if (!posId) {
            alert('Cannot remove position: missing id');
            return;
        }
        const response = await fetch(`${API_URL}/v2/positions/${posId}`, { method: 'DELETE', headers: { 'X-API-Key': API_KEY } });
        const data = await response.json();

        if (data.status === 'deleted' || data.status === 'removed') {
            openPositions = openPositions.filter(p => (p.position_id || p.id || p.signal_id) !== posId);
            renderPositionsEnhanced();
            updatePositionsCount();
            updatePositionChartTabs();
        } else {
            alert('Failed to remove position: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error removing position:', error);
        alert('Failed to remove position');
    }
}

// Credit structures where entry_price is premium received (must match backend CREDIT_STRUCTURES)
const CREDIT_STRUCTURES = new Set([
    'credit_spread', 'put_credit_spread', 'bull_put_spread',
    'call_credit_spread', 'bear_call_spread',
    'iron_condor', 'iron_butterfly',
    'short_call', 'naked_call', 'short_put', 'naked_put',
    'cash_secured_put', 'covered_call',
]);

function updateCloseSummary() {
    if (!closingPosition) return;

    const exitPrice = parseFloat(document.getElementById('positionExitPrice').value) || 0;
    const closeQty = parseFloat(document.getElementById('closeQuantity').value) || 0;

    if (exitPrice && closeQty) {
        const struct = (closingPosition.structure || '').toLowerCase();
        const isStock = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'].includes(struct);
        const isCredit = CREDIT_STRUCTURES.has(struct);
        const multiplier = isStock ? 1 : 100;
        let pnl;
        if (isStock) {
            if (closingPosition.direction === 'SHORT') {
                pnl = (closingPosition.entry_price - exitPrice) * closeQty;
            } else {
                pnl = (exitPrice - closingPosition.entry_price) * closeQty;
            }
        } else if (isCredit) {
            // Credit: received premium at open, pay to close
            pnl = (closingPosition.entry_price - exitPrice) * closeQty * multiplier;
        } else {
            // Debit: paid premium at open, receive to close
            pnl = (exitPrice - closingPosition.entry_price) * closeQty * multiplier;
        }

        const pnlStr = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
        const pnlEl = document.getElementById('closeRealizedPnL');
        pnlEl.textContent = pnlStr;
        pnlEl.className = pnl >= 0 ? 'positive' : 'negative';
    }
}

async function confirmPositionClose() {
    if (!closingPosition) return;
    
    const exitPrice = parseFloat(document.getElementById('positionExitPrice').value);
    const closeQty = parseFloat(document.getElementById('closeQuantity').value);
    
    if (!exitPrice || !closeQty) {
        alert('Please enter exit price and quantity');
        return;
    }
    
    if (closeQty > closingPosition.quantity) {
        alert('Cannot close more than you own');
        return;
    }
    
    // Calculate P&L to determine if this is a loss (must match backend + updateCloseSummary)
    const entryPrice = closingPosition.entry_price || 0;
    const closeStruct = (closingPosition.structure || '').toLowerCase();
    const closeIsStock = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'].includes(closeStruct);
    const closeIsCredit = CREDIT_STRUCTURES.has(closeStruct);
    let pnl;
    if (closeIsStock) {
        if (closingPosition.direction === 'SHORT') {
            pnl = (entryPrice - exitPrice) * closeQty;
        } else {
            pnl = (exitPrice - entryPrice) * closeQty;
        }
    } else if (closeIsCredit) {
        pnl = (entryPrice - exitPrice) * closeQty * 100;
    } else {
        pnl = (exitPrice - entryPrice) * closeQty * 100;
    }
    
    // Determine trade outcome
    let tradeOutcome;
    if (pnl > 0) {
        tradeOutcome = 'WIN';
    } else if (pnl < 0) {
        tradeOutcome = 'LOSS';
    } else {
        tradeOutcome = 'BREAKEVEN';
    }
    
    // If it's a loss, show loss classification modal
    if (tradeOutcome === 'LOSS') {
        showLossClassificationModal(closingPosition, exitPrice, closeQty, pnl);
        return;
    }
    
    // Otherwise, proceed with close
    await executePositionClose(closingPosition.id, exitPrice, closeQty, tradeOutcome, null, null);
}

function showLossClassificationModal(position, exitPrice, closeQty, pnl) {
    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal loss-modal">
            <div class="modal-header">
                <h3>Loss Classification - ${position.ticker}</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="loss-summary">
                    <p class="loss-amount">Loss: <span class="negative">$${Math.abs(pnl).toFixed(2)}</span></p>
                </div>
                <p>What caused this loss? (for backtesting analysis)</p>
                <div class="loss-reasons">
                    <label class="loss-reason setup-failed">
                        <input type="radio" name="lossReason" value="SETUP_FAILED">
                        <span>Setup Failed</span>
                        <small>The trade thesis was wrong - the setup didn't work as expected</small>
                    </label>
                    <label class="loss-reason execution-error">
                        <input type="radio" name="lossReason" value="EXECUTION_ERROR">
                        <span>Execution Error</span>
                        <small>I made a mistake - bad entry, moved stop, over-leveraged, etc.</small>
                    </label>
                    <label class="loss-reason market-conditions">
                        <input type="radio" name="lossReason" value="MARKET_CONDITIONS" checked>
                        <span>Market Conditions</span>
                        <small>Unexpected news, volatility, or market-wide move against position</small>
                    </label>
                </div>
                <div class="modal-field">
                    <label>Notes (optional)</label>
                    <textarea id="lossNotes" placeholder="What did you learn from this trade?"></textarea>
                </div>
                <div class="modal-field">
                    <label>
                        <input type="checkbox" id="stopHitCheck">
                        Stop loss was hit (triggered automatically)
                    </label>
                </div>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn close-position">Confirm Close</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Handle close
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());
    
    // Handle confirm
    modal.querySelector('.modal-btn.close-position').addEventListener('click', async () => {
        const lossReason = modal.querySelector('input[name="lossReason"]:checked')?.value || 'MARKET_CONDITIONS';
        const notes = modal.querySelector('#lossNotes').value;
        const stopHit = modal.querySelector('#stopHitCheck').checked;
        
        modal.remove();
        await executePositionClose(position.id, exitPrice, closeQty, 'LOSS', lossReason, notes, stopHit);
    });
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function executePositionClose(positionId, exitPrice, closeQty, tradeOutcome, lossReason, notes, stopHit = false) {
    try {
        // Save reference before modal close might null it
        const position = closingPosition;

        // Try v2 close endpoint first (creates trade record automatically)
        let response;
        let data;
        if (!position || !position.position_id) {
            alert('Cannot close position: missing position_id');
            return;
        }

        // Compute exit_value for closed_positions P&L tracking
        const struct = (position.structure || '').toLowerCase();
        const stockStructures = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'];
        const isStockClose = stockStructures.includes(struct) || (!struct && position.asset_type === 'EQUITY');
        const multiplier = isStockClose ? 1 : 100;
        const exitValue = Math.round(exitPrice * multiplier * closeQty * 100) / 100;

        // Derive close_reason from outcome
        const closeReason = lossReason ? 'loss' : (tradeOutcome === 'WIN' ? 'profit' : 'manual');

        response = await fetch(`${API_URL}/v2/positions/${position.position_id}/close`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                exit_price: exitPrice,
                quantity: closeQty,
                exit_value: exitValue,
                trade_outcome: tradeOutcome,
                loss_reason: lossReason || null,
                close_reason: closeReason,
                notes: notes || null
            })
        });
        data = await response.json();

        if (data.status === 'success' || data.status === 'closed' || data.status === 'partial_close') {
            closePositionCloseModal();
            await loadOpenPositionsEnhanced();
            updateCurrentPrices();

            // Remove chart tab if fully closed
            if (position && closeQty >= position.quantity) {
                removePositionChartTab(position.ticker);
                if (window.activePriceLevels) {
                    delete window.activePriceLevels[position.ticker];
                }
            }

            const outcome = data.trade_outcome || tradeOutcome;
            console.log(`Position closed: ${position?.ticker} - ${outcome} - P&L: $${data.realized_pnl?.toFixed(2) || '--'}`);

            // BUG 6: Warn if cash adjustment failed
            if (data.cash_adjusted === false) {
                console.warn('Cash adjustment failed for position close — portfolio cash may be inaccurate');
            }
        } else {
            alert('Failed to close position: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error closing position:', error);
        alert('Failed to close position');
    }
}

// ==========================================
// UNIFIED POSITION ENTRY FORM (Brief 10 — C3)
// ==========================================

function openUnifiedPositionModal() {
    let modal = document.getElementById('unifiedPositionModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'unifiedPositionModal';
        modal.className = 'signal-modal-overlay';
        modal.innerHTML = `
            <div class="signal-modal unified-position-modal">
                <div class="modal-header">
                    <h3>Add Position</h3>
                    <button class="modal-close" id="closeUnifiedPositionModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-row">
                        <label>Account</label>
                        <select id="upAccount">
                            <option value="ROBINHOOD">Robinhood</option>
                            <option value="FIDELITY_ROTH">Fidelity Roth</option>
                            <option value="FIDELITY_401A">Fidelity 401A</option>
                        </select>
                    </div>
                    <div class="form-row">
                        <label>Ticker</label>
                        <input type="text" id="upTicker" placeholder="SPY" style="text-transform: uppercase;">
                    </div>
                    <div class="form-row">
                        <label>Structure</label>
                        <select id="upStructure">
                            <option value="stock">Stock</option>
                            <option value="long_call">Long Call</option>
                            <option value="long_put">Long Put</option>
                            <option value="put_credit_spread" selected>Put Credit Spread</option>
                            <option value="put_debit_spread">Put Debit Spread</option>
                            <option value="call_credit_spread">Call Credit Spread</option>
                            <option value="call_debit_spread">Call Debit Spread</option>
                            <option value="iron_condor">Iron Condor</option>
                            <option value="iron_butterfly">Iron Butterfly</option>
                            <option value="straddle">Straddle</option>
                            <option value="strangle">Strangle</option>
                            <option value="custom">Custom (enter below)</option>
                        </select>
                    </div>
                    <div class="form-row custom-structure-field" style="display:none;">
                        <label>Custom Structure Name</label>
                        <input type="text" id="upCustomStructure" placeholder="e.g. broken_wing_butterfly">
                    </div>
                    <div class="form-row spread-fields">
                        <label>Long Strike</label>
                        <input type="number" id="upLongStrike" step="0.5" placeholder="48">
                    </div>
                    <div class="form-row spread-fields">
                        <label>Short Strike</label>
                        <input type="number" id="upShortStrike" step="0.5" placeholder="50">
                    </div>
                    <div class="form-row options-fields">
                        <label>Expiry</label>
                        <input type="date" id="upExpiry">
                    </div>
                    <div class="form-row">
                        <label>Net Premium / Entry Price</label>
                        <input type="number" id="upEntryPrice" step="0.01" placeholder="0.35">
                    </div>
                    <div class="form-row">
                        <label>Quantity</label>
                        <input type="number" id="upQuantity" value="1" min="1">
                    </div>
                    <div class="form-row">
                        <label>Stop Loss</label>
                        <input type="number" id="upStopLoss" step="0.01" placeholder="Optional">
                    </div>
                    <div class="form-row">
                        <label>Target</label>
                        <input type="number" id="upTarget" step="0.01" placeholder="Optional">
                    </div>
                    <div class="form-row">
                        <label>Notes</label>
                        <input type="text" id="upNotes" placeholder="Optional">
                    </div>
                    <div class="risk-calc-preview" id="upRiskPreview"></div>
                </div>
                <div class="modal-actions">
                    <button class="modal-btn cancel" id="upCancel">Cancel</button>
                    <button class="modal-btn accept" id="upSubmit">Add Position</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Events
        document.getElementById('closeUnifiedPositionModal').addEventListener('click', () => modal.classList.remove('active'));
        document.getElementById('upCancel').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
        document.getElementById('upSubmit').addEventListener('click', submitUnifiedPosition);
        document.getElementById('upStructure').addEventListener('change', updateUnifiedFormFields);

        // Auto-calculate risk on input change
        ['upLongStrike', 'upShortStrike', 'upEntryPrice', 'upQuantity'].forEach(id => {
            document.getElementById(id).addEventListener('input', updateRiskPreview);
        });
    }

    // Clear form on each open
    const acctDefault = (activePositionsAccount !== 'ALL' && activePositionsAccount !== 'FIDELITY')
        ? activePositionsAccount : 'ROBINHOOD';
    document.getElementById('upAccount').value = acctDefault;
    document.getElementById('upTicker').value = '';
    document.getElementById('upStructure').value = 'put_credit_spread';
    document.getElementById('upLongStrike').value = '';
    document.getElementById('upShortStrike').value = '';
    document.getElementById('upExpiry').value = '';
    document.getElementById('upEntryPrice').value = '';
    document.getElementById('upQuantity').value = '1';
    document.getElementById('upStopLoss').value = '';
    document.getElementById('upTarget').value = '';
    document.getElementById('upNotes').value = '';
    const customInput = document.getElementById('upCustomStructure');
    if (customInput) customInput.value = '';
    updateUnifiedFormFields();
    document.getElementById('upRiskPreview').innerHTML = '';
    modal.classList.add('active');
}

function updateUnifiedFormFields() {
    const structure = document.getElementById('upStructure').value;
    const isCustom = structure === 'custom';
    const multiStrike = ['straddle', 'strangle', 'iron_condor', 'iron_butterfly'];
    const isSpread = structure.includes('spread') || multiStrike.includes(structure) || isCustom;
    const isOptions = structure !== 'stock';

    document.querySelectorAll('.spread-fields').forEach(el => el.style.display = isSpread ? '' : 'none');
    document.querySelectorAll('.options-fields').forEach(el => el.style.display = isOptions ? '' : 'none');
    document.querySelectorAll('.custom-structure-field').forEach(el => el.style.display = isCustom ? '' : 'none');
}

function updateRiskPreview() {
    const structure = document.getElementById('upStructure').value;
    const longStrike = parseFloat(document.getElementById('upLongStrike').value) || 0;
    const shortStrike = parseFloat(document.getElementById('upShortStrike').value) || 0;
    const entryPrice = parseFloat(document.getElementById('upEntryPrice').value) || 0;
    const quantity = parseInt(document.getElementById('upQuantity').value) || 1;
    const preview = document.getElementById('upRiskPreview');

    if (!entryPrice) { preview.innerHTML = ''; return; }

    const isSpread = structure.includes('spread') || structure === 'iron_condor' || structure === 'iron_butterfly' || structure === 'custom';
    const isStock = structure === 'stock';

    if (isStock) {
        const maxLoss = entryPrice * quantity;
        preview.innerHTML = `<div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)} (full position)</div>`;
        return;
    }

    if (isSpread && longStrike && shortStrike) {
        const width = Math.abs(shortStrike - longStrike);
        const isCredit = structure.includes('credit');
        const premium = Math.abs(entryPrice);
        const maxLoss = isCredit ? (width - premium) * 100 * quantity : premium * 100 * quantity;
        const maxProfit = isCredit ? premium * 100 * quantity : (width - premium) * 100 * quantity;
        preview.innerHTML = `
            <div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)}</div>
            <div class="risk-preview-line">Max Profit: $${maxProfit.toFixed(2)}</div>
        `;
    } else if (!isStock) {
        const premium = Math.abs(entryPrice);
        const maxLoss = premium * 100 * quantity;
        preview.innerHTML = `<div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)} (premium paid)</div>`;
    }
}

async function submitUnifiedPosition() {
    const ticker = document.getElementById('upTicker').value.trim().toUpperCase();
    if (!ticker) { alert('Enter a ticker'); return; }

    let structure = document.getElementById('upStructure').value;
    if (structure === 'custom') {
        structure = document.getElementById('upCustomStructure').value.trim().toLowerCase().replace(/\s+/g, '_');
        if (!structure) { alert('Enter a custom structure name'); return; }
    }
    const entryPrice = parseFloat(document.getElementById('upEntryPrice').value);
    if (!entryPrice && entryPrice !== 0) { alert('Enter an entry price/premium'); return; }

    const body = {
        ticker: ticker,
        asset_type: structure === 'stock' ? 'EQUITY' : 'OPTION',
        structure: structure,
        entry_price: entryPrice,
        quantity: parseInt(document.getElementById('upQuantity').value) || 1,
        source: 'MANUAL',
        account: document.getElementById('upAccount').value,
    };

    const longStrike = parseFloat(document.getElementById('upLongStrike').value);
    const shortStrike = parseFloat(document.getElementById('upShortStrike').value);
    const expiry = document.getElementById('upExpiry').value;
    const stopLoss = parseFloat(document.getElementById('upStopLoss').value);
    const target = parseFloat(document.getElementById('upTarget').value);
    const notes = document.getElementById('upNotes').value.trim();

    if (longStrike) body.long_strike = longStrike;
    if (shortStrike) body.short_strike = shortStrike;
    if (expiry) body.expiry = expiry;
    if (stopLoss) body.stop_loss = stopLoss;
    if (target) body.target_1 = target;
    if (notes) body.notes = notes;

    try {
        const response = await fetch(`${API_URL}/v2/positions`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
        });
        const data = await response.json();

        if (data.status === 'created' || data.status === 'combined') {
            document.getElementById('unifiedPositionModal').classList.remove('active');
            await loadOpenPositionsEnhanced();
            addPositionChartTab(ticker);
            updateCurrentPrices();
            if (data.status === 'combined') {
                console.log('Position combined:', data.detail);
            }
        } else {
            alert('Failed to create position: ' + (data.detail || JSON.stringify(data)));
        }
    } catch (error) {
        console.error('Error creating position:', error);
        alert('Failed to create position');
    }
}

// ==========================================
// POSITION EDIT MODAL (Brief 10 — C2)
// ==========================================

function openPositionEditModal(position) {
    let modal = document.getElementById('positionEditModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'positionEditModal';
        modal.className = 'signal-modal-overlay';
        modal.innerHTML = `
            <div class="signal-modal">
                <div class="modal-header">
                    <h3 id="editModalTitle">Edit Position</h3>
                    <button class="modal-close" id="closeEditModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="edit-position-info" id="editPositionInfo"></div>
                    <div class="form-row">
                        <label>Account</label>
                        <input type="text" id="editPositionAccount" readonly style="opacity: 0.6; cursor: not-allowed;">
                    </div>
                    <div class="form-row">
                        <label>Entry Price</label>
                        <input type="number" id="editEntryPrice" step="0.01" min="0">
                    </div>
                    <div class="form-row">
                        <label>Quantity</label>
                        <input type="number" id="editQuantity" min="1" step="1">
                    </div>
                    <div class="form-row">
                        <label>Stop Loss</label>
                        <input type="number" id="editStopLoss" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Target</label>
                        <input type="number" id="editTarget" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Current Price</label>
                        <input type="number" id="editCurrentPrice" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Notes</label>
                        <input type="text" id="editNotes">
                    </div>
                    <div class="edit-add-section">
                        <div class="edit-add-header">Add to Position</div>
                        <div class="form-row-inline">
                            <div class="form-row">
                                <label id="editAddQtyLabel">Additional Qty</label>
                                <input type="number" id="editAddQty" min="1" step="1" placeholder="0">
                            </div>
                            <div class="form-row">
                                <label id="editAddCostLabel">Cost per Contract</label>
                                <input type="number" id="editAddCost" step="0.01" placeholder="0.00">
                            </div>
                        </div>
                        <div class="edit-add-preview" id="editAddPreview"></div>
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="modal-btn cancel" id="editCancel">Cancel</button>
                    <button class="modal-btn accept" id="editSave">Save</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        document.getElementById('closeEditModal').addEventListener('click', () => modal.classList.remove('active'));
        document.getElementById('editCancel').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }

    document.getElementById('editModalTitle').textContent = `Edit ${position.ticker}`;
    document.getElementById('editEntryPrice').value = position.entry_price || '';
    document.getElementById('editStopLoss').value = position.stop_loss || '';
    document.getElementById('editPositionAccount').value = position.account || 'ROBINHOOD';
    document.getElementById('editTarget').value = position.target_1 || '';
    document.getElementById('editCurrentPrice').value = position.current_price || '';
    document.getElementById('editNotes').value = position.notes || '';
    document.getElementById('editAddQty').value = '';
    document.getElementById('editAddCost').value = '';

    // Show current position info
    const infoEl = document.getElementById('editPositionInfo');
    const curQty = position.quantity || 0;
    const curEntry = position.entry_price || 0;
    const isStock = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'].includes((position.structure || '').toLowerCase()) || (!position.structure && position.asset_type === 'EQUITY');
    const unitLabel = isStock ? 'shares' : 'contracts';
    const dirLabel = position.direction === 'SHORT' ? ' (SHORT)' : '';
    infoEl.innerHTML = `<span>Current: ${curQty} ${unitLabel}${dirLabel} @ $${curEntry.toFixed(2)}</span>`;

    // Stock-aware labels
    document.getElementById('editAddCostLabel').textContent = isStock ? 'Cost per Share' : 'Cost per Contract';
    document.getElementById('editAddQtyLabel').textContent = isStock ? 'Additional Shares' : 'Additional Contracts';

    // Populate direct quantity field
    document.getElementById('editQuantity').value = position.quantity || '';

    // Live preview of cost basis recalc
    const previewEl = document.getElementById('editAddPreview');
    const updatePreview = () => {
        const addQty = parseInt(document.getElementById('editAddQty').value) || 0;
        const addCost = parseFloat(document.getElementById('editAddCost').value) || 0;
        if (addQty > 0 && addCost > 0) {
            const newTotalQty = curQty + addQty;
            const newAvgCost = ((curEntry * curQty) + (addCost * addQty)) / newTotalQty;
            previewEl.innerHTML = `New: ${newTotalQty} ${unitLabel} @ $${newAvgCost.toFixed(2)} avg`;
        } else {
            previewEl.innerHTML = '';
        }
    };
    document.getElementById('editAddQty').addEventListener('input', updatePreview);
    document.getElementById('editAddCost').addEventListener('input', updatePreview);

    // Rebind save button
    const saveBtn = document.getElementById('editSave');
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    newSaveBtn.addEventListener('click', async () => {
        const posId = position.position_id || position.id;
        const updates = {};
        const epVal = document.getElementById('editEntryPrice').value.trim();
        const slVal = document.getElementById('editStopLoss').value.trim();
        const tgtVal = document.getElementById('editTarget').value.trim();
        const cpVal = document.getElementById('editCurrentPrice').value.trim();
        const notes = document.getElementById('editNotes').value.trim();
        if (epVal !== '' && parseFloat(epVal) !== curEntry) updates.entry_price = parseFloat(epVal);
        if (slVal !== '') updates.stop_loss = parseFloat(slVal);
        if (tgtVal !== '') updates.target_1 = parseFloat(tgtVal);
        if (cpVal !== '') updates.current_price = parseFloat(cpVal);
        if (notes) updates.notes = notes;

        // Handle direct quantity edit
        const qtyVal = document.getElementById('editQuantity').value.trim();
        if (qtyVal !== '' && parseInt(qtyVal) !== curQty) {
            updates.quantity = parseInt(qtyVal);
            const costMultiplierDirect = isStock ? 1 : 100;
            updates.cost_basis = parseFloat((curEntry * parseInt(qtyVal) * costMultiplierDirect).toFixed(2));
        }

        // Handle "Add to Position" (takes precedence over direct qty edit)
        const addQty = parseInt(document.getElementById('editAddQty').value) || 0;
        const addCost = parseFloat(document.getElementById('editAddCost').value) || 0;
        if (addQty > 0 && addCost > 0) {
            const newTotalQty = curQty + addQty;
            const newAvgCost = ((curEntry * curQty) + (addCost * addQty)) / newTotalQty;
            updates.quantity = newTotalQty;
            updates.entry_price = parseFloat(newAvgCost.toFixed(4));
            const costMultiplier = isStock ? 1 : 100;
            updates.cost_basis = parseFloat((newAvgCost * newTotalQty * costMultiplier).toFixed(2));
        }

        if (Object.keys(updates).length === 0) { alert('No changes'); return; }

        try {
            const response = await fetch(`${API_URL}/v2/positions/${posId}`, {
                method: 'PATCH',
                headers: authHeaders(),
                body: JSON.stringify(updates)
            });
            const data = await response.json();
            if (data.status === 'updated') {
                modal.classList.remove('active');
                await loadOpenPositionsEnhanced();
            } else {
                alert('Failed to update: ' + (data.detail || JSON.stringify(data)));
            }
        } catch (error) {
            console.error('Error updating position:', error);
            alert('Failed to update position');
        }
    });

    modal.classList.add('active');
}

// Auto-scale chart tab font/padding so all tickers fit in one row
function autoScaleChartTabs() {
    const container = document.getElementById('chartTabs');
    if (!container) return;
    const tabs = container.querySelectorAll('.chart-tab');
    const count = tabs.length;
    let fontSize, padding;
    if (count <= 5) {
        fontSize = '14px'; padding = '12px 24px';
    } else if (count <= 8) {
        fontSize = '12px'; padding = '10px 14px';
    } else if (count <= 12) {
        fontSize = '11px'; padding = '8px 10px';
    } else {
        fontSize = '10px'; padding = '6px 7px';
    }
    tabs.forEach(t => {
        t.style.fontSize = fontSize;
        t.style.padding = padding;
    });
}

// Chart tabs for open positions
function addPositionChartTab(ticker) {
    const tabsContainer = document.getElementById('chartTabs');
    if (!tabsContainer) return;
    
    // Check if tab already exists
    const existing = tabsContainer.querySelector(`[data-symbol="${ticker}"]`);
    if (existing) return;
    
    const tab = document.createElement('button');
    tab.className = 'chart-tab position-tab';
    tab.dataset.symbol = ticker;
    tab.textContent = ticker;
    tab.addEventListener('click', () => changeChartSymbol(ticker));
    
    tabsContainer.appendChild(tab);
    autoScaleChartTabs();
}

function removePositionChartTab(ticker) {
    const tabsContainer = document.getElementById('chartTabs');
    if (!tabsContainer) return;
    
    // Don't remove default tabs
    if (['SPY', 'VIX', 'BTCUSD'].includes(ticker)) return;
    
    // Check if any other position still has this ticker
    const stillHasPosition = openPositions.some(p => p.ticker === ticker);
    if (stillHasPosition) return;
    
    const tab = tabsContainer.querySelector(`[data-symbol="${ticker}"]`);
    if (tab && tab.classList.contains('position-tab')) {
        tab.remove();
        autoScaleChartTabs();
    }
}

function updatePositionChartTabs() {
    // Add tabs for all open positions
    openPositions.forEach(pos => {
        addPositionChartTab(pos.ticker);
    });
    autoScaleChartTabs();
}

// Price updates for real-time P&L
async function triggerMarkToMarket() {
    try {
        await fetch(`${API_URL}/v2/positions/mark-to-market`, {
            method: 'POST',
            headers: authHeaders()
        });
    } catch (e) {
        console.warn('MTM trigger failed:', e);
    }
}

async function refreshPositions() {
    const refreshBtn = document.getElementById('positionsRefreshBtn');
    if (refreshBtn) {
        refreshBtn.classList.add('refreshing');
        refreshBtn.disabled = true;
    }
    try {
        // MTM first — fetches live Polygon prices for options, updates DB
        await triggerMarkToMarket();
        // Then reload positions (now with updated current_price + unrealized_pnl from DB)
        await loadOpenPositionsEnhanced();
        await updateCurrentPrices();
    } finally {
        if (refreshBtn) {
            refreshBtn.classList.remove('refreshing');
            refreshBtn.disabled = false;
        }
    }
}

function startPriceUpdates() {
    // Update every 30 seconds
    priceUpdateInterval = setInterval(updateCurrentPrices, 60000);
    // Initial update
    updateCurrentPrices();
}

async function updateCurrentPrices() {
    if (openPositions.length === 0) return;
    
    const tickers = [...new Set(openPositions.map(p => p.ticker))];
    
    for (const ticker of tickers) {
        try {
            // Try to get price from hybrid scanner (it's fast)
            const response = await fetch(`${API_URL}/hybrid/price/${ticker}`);
            const data = await response.json();
            if (data.price) {
                currentPrices[ticker] = data.price;
            }
        } catch (error) {
            // Silently fail - we'll use entry price as fallback
        }
    }
    
    // Re-render with updated prices
    renderPositionsEnhanced();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initPositionModals, 1300);
    setTimeout(initManualPositionModal, 1400);
    setTimeout(initKnowledgebase, 1500);
});


// ============================================
// MANUAL POSITION ENTRY
// ============================================

function initManualPositionModal() {
    const modal = document.getElementById('manualPositionModal');
    const closeBtn = document.getElementById('closeManualPositionBtn');
    const cancelBtn = document.getElementById('cancelManualPositionBtn');
    const confirmBtn = document.getElementById('confirmManualPositionBtn');
    
    document.querySelectorAll('[data-action="add-manual-position"]').forEach((btn) => {
        btn.addEventListener('click', () => {
            openUnifiedPositionModal();
        });
    });
    
    if (closeBtn) closeBtn.addEventListener('click', closeManualPositionModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeManualPositionModal);
    if (confirmBtn) confirmBtn.addEventListener('click', submitManualPosition);
    
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeManualPositionModal();
        });
    }
    
    // Auto-uppercase ticker input
    const tickerInput = document.getElementById('manualTicker');
    if (tickerInput) {
        tickerInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
        });
    }
    
    console.log('ðŸ“ Manual position modal initialized');
}

function openManualPositionModal(context = 'equity') {
    const modal = document.getElementById('manualPositionModal');
    const tickerEl = document.getElementById('manualTicker');
    const quantityEl = document.getElementById('manualQuantity');
    const accountEl = document.getElementById('manualAccount');
    const assetClassEl = document.getElementById('manualAssetClass');

    manualPositionContext = (context || 'equity').toLowerCase();

    if (modal) {
        // Clear form
        tickerEl.value = '';
        document.getElementById('manualDirection').value = 'LONG';
        document.getElementById('manualEntryPrice').value = '';
        quantityEl.value = '';
        document.getElementById('manualStopLoss').value = '';
        document.getElementById('manualTarget').value = '';
        document.getElementById('manualNotes').value = '';

        if (manualPositionContext === 'crypto') {
            if (accountEl) accountEl.value = 'BREAKOUT';
            if (assetClassEl) assetClassEl.value = 'CRYPTO';
            if (tickerEl) tickerEl.placeholder = 'BTCUSDT';
            if (quantityEl) {
                quantityEl.step = '0.001';
                quantityEl.placeholder = '0.010';
            }
        } else {
            if (accountEl) accountEl.value = 'MANUAL';
            if (assetClassEl) assetClassEl.value = 'EQUITY';
            if (tickerEl) tickerEl.placeholder = 'AAPL';
            if (quantityEl) {
                quantityEl.step = '1';
                quantityEl.placeholder = '100';
            }
        }
        
        modal.classList.add('active');
        tickerEl.focus();
    }
}

function closeManualPositionModal() {
    const modal = document.getElementById('manualPositionModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function submitManualPosition() {
    const ticker = document.getElementById('manualTicker').value.trim().toUpperCase();
    const direction = document.getElementById('manualDirection').value;
    const entryPrice = parseFloat(document.getElementById('manualEntryPrice').value);
    const quantity = parseFloat(document.getElementById('manualQuantity').value);
    const stopLoss = parseFloat(document.getElementById('manualStopLoss').value) || null;
    const target = parseFloat(document.getElementById('manualTarget').value) || null;
    const notes = document.getElementById('manualNotes').value.trim();
    const account = document.getElementById('manualAccount')?.value || (manualPositionContext === 'crypto' ? 'BREAKOUT' : 'MANUAL');
    const selectedAssetClass = document.getElementById('manualAssetClass')?.value || 'EQUITY';
    
    // Validation
    if (!ticker) {
        alert('Please enter a ticker symbol');
        return;
    }
    if (isNaN(entryPrice) || entryPrice <= 0) {
        alert('Please enter a valid entry price');
        return;
    }
    if (isNaN(quantity) || quantity <= 0) {
        alert('Please enter a valid quantity');
        return;
    }
    
    // Determine asset class
    const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
    const isCrypto = selectedAssetClass === 'CRYPTO'
        || manualPositionContext === 'crypto'
        || cryptoTickers.some(c => ticker.includes(c));
    const strategy = account === 'BREAKOUT' ? 'Breakout Manual' : 'Manual Entry';
    
    const positionData = {
        ticker: ticker,
        direction: direction,
        entry_price: entryPrice,
        quantity: quantity,
        stop_loss: stopLoss,
        target_1: target,
        strategy: strategy,
        asset_class: isCrypto ? 'CRYPTO' : 'EQUITY',
        signal_type: 'MANUAL',
        notes: notes,
        account: account
    };
    
    try {
        const response = await fetch(`${API_URL}/v2/positions`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(positionData)
        });

        const result = await response.json();

        if (response.ok) {
            console.log('Manual position created:', result);
            closeManualPositionModal();

            // Refresh positions from server
            await loadOpenPositionsEnhanced();
            updateCurrentPrices();
        } else {
            alert(`Error: ${result.detail || 'Failed to create position'}`);
        }
    } catch (error) {
        console.error('Error creating manual position:', error);
        alert('Failed to create position. Please try again.');
    }
}

// ============================================
// KNOWLEDGEBASE POPUP FUNCTIONALITY
// ============================================

let kbTermMap = {};
let kbPopupModal = null;

async function initKnowledgebase() {
    // Load term map for making UI terms clickable
    try {
        const response = await fetch(`${API_URL}/knowledgebase/term-map`);
        const data = await response.json();
        kbTermMap = data.termMap || {};
        console.log(`ðŸ“š Loaded ${Object.keys(kbTermMap).length} knowledgebase terms`);
    } catch (error) {
        console.error('Error loading knowledgebase term map:', error);
    }
    
    // Initialize popup modal
    kbPopupModal = document.getElementById('kbPopupModal');
    
    // Close button
    const closeBtn = document.getElementById('closeKbPopupBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeKbPopup);
    }
    
    // Close on backdrop click
    if (kbPopupModal) {
        kbPopupModal.addEventListener('click', (e) => {
            if (e.target === kbPopupModal) closeKbPopup();
        });
    }
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && kbPopupModal?.classList.contains('active')) {
            closeKbPopup();
        }
    });
    
    // Initialize all KB links and info icons in the page
    initKbClickHandlers();
}

// Initialize click handlers for all KB links and info icons
function initKbClickHandlers() {
    // Handle .kb-link elements (clickable text headers/labels)
    document.querySelectorAll('.kb-link[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    // Handle .kb-info-icon elements (â“˜ icons)
    document.querySelectorAll('.kb-info-icon[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    // Handle .kb-factor-link elements (clickable factor names in settings modals)
    document.querySelectorAll('.kb-factor-link[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    console.log('ðŸ“š KB click handlers initialized');
}

// Map strategy/signal names to KB term IDs
const KB_TERM_MAP = {
    // Strategies
    'TRIPLE_LINE': 'triple-line-trend',
    'TRIPLE LINE': 'triple-line-trend',
    'CTA': 'cta-scanner',
    'CTA_GOLDEN': 'cta-scanner',
    'CTA_TWOCLOSE': 'cta-scanner',
    'CTA_PULLBACK': 'cta-scanner',
    'GOLDEN_TOUCH': 'cta-scanner',
    'GOLDEN TOUCH': 'cta-scanner',
    'TWO_CLOSE': 'cta-scanner',
    'TWO-CLOSE': 'cta-scanner',
    'PULLBACK': 'cta-scanner',
    'HUNTER': 'hunter-scanner',
    'URSA': 'hunter-scanner',
    'TAURUS': 'hunter-scanner',
    'EXHAUSTION': 'trade-ideas',
    'EXHAUSTION_BULL': 'trade-ideas',
    'EXHAUSTION_BEAR': 'trade-ideas',
    
    // Signal types
    'LONG': 'risk-on',
    'SHORT': 'risk-off',
    'BULLISH': 'toro-major',
    'BEARISH': 'ursa-major',
    
    // CTA Zones
    'MAX_LONG': 'max-long',
    'MAX LONG': 'max-long',
    'DE_LEVERAGING': 'de-leveraging',
    'DE-LEVERAGING': 'de-leveraging',
    'DELEVERAGING': 'de-leveraging',
    'WATERFALL': 'waterfall',
    'CAPITULATION': 'capitulation',
    
    // Bias levels
    'TORO_MAJOR': 'toro-major',
    'TORO_MINOR': 'toro-minor',
    'URSA_MAJOR': 'ursa-major',
    'URSA_MINOR': 'ursa-minor',
    'NEUTRAL': 'neutral',
    
    // BTC signals
    '25-DELTA SKEW': 'btc-bottom-signals',
    'QUARTERLY BASIS': 'btc-bottom-signals',
    'PERP FUNDING': 'btc-bottom-signals',
    'STABLECOIN APRS': 'btc-bottom-signals',
    'TERM STRUCTURE': 'btc-bottom-signals',
    'OPEN INTEREST': 'btc-bottom-signals',
    'LIQUIDATION': 'btc-bottom-signals',
    'ORDERBOOK SKEW': 'btc-bottom-signals',
    'VIX SPIKE': 'vix-term-structure',
    
    // Options flow
    'SWEEP': 'trade-ideas',
    'BLOCK': 'trade-ideas',
    'DARK_POOL': 'trade-ideas',
    'UNUSUAL_VOLUME': 'trade-ideas'
};

// Helper to get KB term ID from a name
function getKbTermId(name) {
    if (!name) return null;
    const normalized = name.toUpperCase().trim();
    return KB_TERM_MAP[normalized] || null;
}

// Helper to wrap text with KB link if a mapping exists
function wrapWithKbLink(text, customTermId = null) {
    const termId = customTermId || getKbTermId(text);
    if (termId) {
        return `<span class="kb-term-dynamic" data-kb-term="${termId}">${text}</span>`;
    }
    return text;
}

// Attach click handlers to dynamically created KB links
function attachDynamicKbHandlers(container) {
    if (!container) return;
    container.querySelectorAll('.kb-term-dynamic[data-kb-term]').forEach(el => {
        // Remove existing listener to avoid duplicates
        el.removeEventListener('click', handleDynamicKbClick);
        el.addEventListener('click', handleDynamicKbClick);
    });
}

function handleDynamicKbClick(e) {
    e.preventDefault();
    e.stopPropagation();
    const termId = e.currentTarget.dataset.kbTerm;
    if (termId) openKbPopup(termId);
}

async function openKbPopup(termId) {
    if (!kbPopupModal) return;
    
    try {
        // Load popup data
        const response = await fetch(`${API_URL}/knowledgebase/popup/${termId}`);
        if (!response.ok) throw new Error('Term not found');
        
        const data = await response.json();
        
        // Populate popup
        document.getElementById('kbPopupCategory').textContent = data.category || 'General';
        document.getElementById('kbPopupTitle').textContent = data.term;
        
        // Format short description with paragraphs
        const formattedDesc = formatPopupDescription(data.shortDescription || '');
        document.getElementById('kbPopupBody').innerHTML = formattedDesc;
        
        // Related terms
        const relatedContainer = document.getElementById('kbPopupRelated');
        if (data.relatedTerms && data.relatedTerms.length > 0) {
            let relatedHtml = '<span style="color: var(--text-secondary); font-size: 12px;">Related: </span>';
            data.relatedTerms.slice(0, 4).forEach(relatedId => {
                // Find term name from map
                const termName = Object.keys(kbTermMap).find(k => kbTermMap[k] === relatedId) || relatedId;
                relatedHtml += `<span class="related-tag" data-term-id="${relatedId}">${termName}</span>`;
            });
            relatedContainer.innerHTML = relatedHtml;
            
            // Add click handlers for related terms
            relatedContainer.querySelectorAll('.related-tag').forEach(tag => {
                tag.addEventListener('click', () => {
                    openKbPopup(tag.dataset.termId);
                });
            });
        } else {
            relatedContainer.innerHTML = '';
        }
        
        // More info link
        const moreInfoLink = document.getElementById('kbMoreInfoLink');
        moreInfoLink.href = `/knowledgebase?entry=${termId}`;
        
        // Show modal
        kbPopupModal.classList.add('active');
        
    } catch (error) {
        console.error('Error loading knowledgebase popup:', error);
    }
}

function closeKbPopup() {
    if (kbPopupModal) {
        kbPopupModal.classList.remove('active');
    }
}

function formatPopupDescription(text) {
    if (!text) return '';
    
    // Split by double newlines for paragraphs
    let html = text;
    
    // Bold text
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Convert newlines to paragraphs
    const paragraphs = html.split('\n\n');
    html = paragraphs.map(p => {
        p = p.trim();
        if (!p) return '';
        // Handle single-line list items
        if (p.startsWith('- ')) {
            return '<p>' + p.replace(/^- /, '- ') + '</p>';
        }
        return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
    }).join('');
    
    return html;
}

// Make a specific term clickable
function makeTermClickable(element, termId) {
    element.classList.add('kb-term');
    element.setAttribute('data-kb-term', termId);
    element.style.cursor = 'pointer';
    element.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        openKbPopup(termId);
    });
}

// Utility function to find and make terms clickable in an element
function linkKnowledgebaseTerms(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (!container) return;
    
    // For each term in our map, find it in the container and make it clickable
    Object.entries(kbTermMap).forEach(([term, id]) => {
        // Skip if term is too short (to avoid matching partial words)
        if (term.length < 4) return;
        
        // Find text nodes containing this term
        const walker = document.createTreeWalker(
            container,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walker.nextNode()) {
            if (node.nodeValue.includes(term) && !node.parentElement.classList.contains('kb-term')) {
                // Wrap the term in a clickable span
                const regex = new RegExp(`(${escapeRegExp(term)})`, 'gi');
                if (regex.test(node.nodeValue)) {
                    const span = document.createElement('span');
                    span.innerHTML = node.nodeValue.replace(regex, `<span class="kb-term" data-kb-term="${id}">$1</span>`);
                    node.parentNode.replaceChild(span, node);
                }
            }
        }
    });
    
    // Add click handlers
    container.querySelectorAll('.kb-term[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openKbPopup(el.dataset.kbTerm);
        });
    });
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Export for use in other parts of the app
window.openKbPopup = openKbPopup;
window.makeTermClickable = makeTermClickable;
window.linkKnowledgebaseTerms = linkKnowledgebaseTerms;

// =========================================================================
// OPTIONS POSITION MANAGEMENT
// =========================================================================

let currentLegCount = 1;

function initOptionsTab() {
    // Modal controls
    document.getElementById('openOptionsModalBtn')?.addEventListener('click', openOptionsModal);
    document.getElementById('closeOptionsModalBtn')?.addEventListener('click', closeOptionsModal);
    document.getElementById('cancelOptionsBtn')?.addEventListener('click', closeOptionsModal);
    document.getElementById('saveOptionsBtn')?.addEventListener('click', saveOptionsPosition);
    document.getElementById('addLegBtn')?.addEventListener('click', addLeg);

    // Strategy change updates direction and leg count
    document.getElementById('optStrategy')?.addEventListener('change', onStrategyChange);

    // Set default entry date to today
    const entryDateInput = document.getElementById('optEntryDate');
    if (entryDateInput) {
        entryDateInput.value = new Date().toISOString().split('T')[0];
    }

    // Close modal on overlay click
    const overlay = document.getElementById('optionsModalOverlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeOptionsModal();
        });
    }

    console.log('Options tab initialized');
}

function openOptionsModal() {
    document.getElementById('optionsModalOverlay').style.display = 'flex';
    currentLegCount = 1;
    // Set default entry date
    const entryDateInput = document.getElementById('optEntryDate');
    if (entryDateInput) {
        entryDateInput.value = new Date().toISOString().split('T')[0];
    }
}

function closeOptionsModal() {
    document.getElementById('optionsModalOverlay').style.display = 'none';
    resetOptionsForm();
}

function resetOptionsForm() {
    const fields = ['optUnderlying', 'optNetPremium', 'optMaxProfit', 'optMaxLoss', 'optBreakeven', 'optThesis'];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const optStrategy = document.getElementById('optStrategy');
    if (optStrategy) optStrategy.value = 'LONG_CALL';

    const optDirection = document.getElementById('optDirection');
    if (optDirection) optDirection.value = 'BULLISH';

    // Reset to single leg
    const container = document.getElementById('optLegsContainer');
    if (container) {
        container.innerHTML = createLegHTML(1);
    }
    currentLegCount = 1;
}

function onStrategyChange(e) {
    const strategy = e.target.value;
    const directionSelect = document.getElementById('optDirection');

    // Auto-set direction based on strategy
    const directionMap = {
        'LONG_CALL': 'BULLISH',
        'LONG_PUT': 'BEARISH',
        'BULL_CALL_SPREAD': 'BULLISH',
        'BEAR_PUT_SPREAD': 'BEARISH',
        'BULL_PUT_SPREAD': 'BULLISH',
        'BEAR_CALL_SPREAD': 'BEARISH',
        'IRON_CONDOR': 'NEUTRAL',
        'STRADDLE': 'VOLATILITY',
        'STRANGLE': 'VOLATILITY'
    };

    if (directionMap[strategy] && directionSelect) {
        directionSelect.value = directionMap[strategy];
    }

    // Auto-set leg count based on strategy
    const legCountMap = {
        'LONG_CALL': 1,
        'LONG_PUT': 1,
        'BULL_CALL_SPREAD': 2,
        'BEAR_PUT_SPREAD': 2,
        'BULL_PUT_SPREAD': 2,
        'BEAR_CALL_SPREAD': 2,
        'IRON_CONDOR': 4,
        'STRADDLE': 2,
        'STRANGLE': 2,
        'CUSTOM': 1
    };

    const targetLegs = legCountMap[strategy] || 1;
    setLegCount(targetLegs);
}

function setLegCount(count) {
    const container = document.getElementById('optLegsContainer');
    if (!container) return;

    container.innerHTML = '';
    for (let i = 1; i <= count; i++) {
        container.innerHTML += createLegHTML(i);
    }
    currentLegCount = count;
}

function createLegHTML(legNum) {
    return `
        <div class="leg-row" data-leg="${legNum}">
            <div class="leg-header">
                <span class="leg-number">Leg ${legNum}</span>
                ${legNum > 1 ? `<button type="button" class="remove-leg-btn" onclick="removeLeg(${legNum})">X</button>` : ''}
            </div>
            <div class="leg-fields">
                <select class="leg-action form-select-sm">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                </select>
                <select class="leg-type form-select-sm">
                    <option value="CALL">CALL</option>
                    <option value="PUT">PUT</option>
                </select>
                <input type="number" class="leg-strike form-input-sm" placeholder="Strike" step="0.5">
                <input type="date" class="leg-expiry form-input-sm">
                <input type="number" class="leg-qty form-input-sm" placeholder="Qty" value="1" min="1">
                <input type="number" class="leg-premium form-input-sm" placeholder="Premium" step="0.01">
            </div>
        </div>
    `;
}

function addLeg() {
    currentLegCount++;
    const container = document.getElementById('optLegsContainer');
    if (container) {
        container.innerHTML += createLegHTML(currentLegCount);
    }
}

function removeLeg(legNum) {
    const legRow = document.querySelector(`.leg-row[data-leg="${legNum}"]`);
    if (legRow) {
        legRow.remove();
        currentLegCount--;
        // Renumber remaining legs
        document.querySelectorAll('.leg-row').forEach((row, idx) => {
            row.dataset.leg = idx + 1;
            row.querySelector('.leg-number').textContent = `Leg ${idx + 1}`;
        });
    }
}

async function saveOptionsPosition() {
    const underlying = document.getElementById('optUnderlying')?.value.trim().toUpperCase();
    const strategy = document.getElementById('optStrategy')?.value;
    const direction = document.getElementById('optDirection')?.value;
    const netPremium = parseFloat(document.getElementById('optNetPremium')?.value) || 0;
    const maxProfit = parseFloat(document.getElementById('optMaxProfit')?.value) || null;
    const maxLoss = parseFloat(document.getElementById('optMaxLoss')?.value) || null;
    const breakevenStr = document.getElementById('optBreakeven')?.value;
    const entryDate = document.getElementById('optEntryDate')?.value;
    const thesis = document.getElementById('optThesis')?.value;

    if (!underlying) {
        alert('Please enter an underlying ticker');
        return;
    }

    // Collect legs
    const legs = [];
    document.querySelectorAll('.leg-row').forEach(row => {
        const action = row.querySelector('.leg-action')?.value;
        const optionType = row.querySelector('.leg-type')?.value;
        const strike = parseFloat(row.querySelector('.leg-strike')?.value);
        const expiry = row.querySelector('.leg-expiry')?.value;
        const qty = parseInt(row.querySelector('.leg-qty')?.value) || 1;
        const premium = parseFloat(row.querySelector('.leg-premium')?.value) || 0;

        if (strike && expiry) {
            legs.push({
                action: action,
                option_type: optionType,
                strike: strike,
                expiration: expiry,
                quantity: qty,
                premium: premium
            });
        }
    });

    if (legs.length === 0) {
        alert('Please add at least one leg with strike and expiration');
        return;
    }

    // Parse breakeven
    let breakeven = [];
    if (breakevenStr) {
        breakeven = breakevenStr.split(',').map(b => parseFloat(b.trim())).filter(b => !isNaN(b));
    }

    // Map strategy_type to unified structure names
    const STRATEGY_TO_STRUCTURE = {
        'LONG_CALL': 'long_call',
        'LONG_PUT': 'long_put',
        'BULL_CALL_SPREAD': 'call_debit_spread',
        'BEAR_PUT_SPREAD': 'put_debit_spread',
        'BULL_PUT_SPREAD': 'put_credit_spread',
        'BEAR_CALL_SPREAD': 'call_credit_spread',
        'IRON_CONDOR': 'iron_condor',
        'STRADDLE': 'straddle',
        'STRANGLE': 'strangle',
        'CUSTOM': 'custom'
    };

    // Extract strikes and expiry from legs
    const strikes = legs.map(l => l.strike).sort((a, b) => a - b);
    const longStrike = strikes[0] || null;
    const shortStrike = strikes.length > 1 ? strikes[strikes.length - 1] : null;
    const expiry = legs[0]?.expiration || null;

    const payload = {
        ticker: underlying,
        asset_type: 'OPTION',
        structure: STRATEGY_TO_STRUCTURE[strategy] || strategy.toLowerCase(),
        direction: direction === 'BULLISH' ? 'LONG' : (direction === 'BEARISH' ? 'SHORT' : direction),
        legs: legs,
        entry_price: Math.abs(netPremium / 100) || 0,
        quantity: legs[0]?.quantity || 1,
        max_profit: maxProfit,
        max_loss: maxLoss,
        expiry: expiry,
        long_strike: longStrike,
        short_strike: shortStrike,
        notes: thesis,
        account: 'ROBINHOOD'
    };

    try {
        const response = await fetch(`${API_URL}/v2/positions`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok) {
            closeOptionsModal();
            loadOptionsPositions();
            console.log(`Options position added: ${underlying} ${strategy}`);
        } else {
            const err = await response.json().catch(() => ({}));
            alert('Error saving position: ' + (err.detail || 'Unknown error'));
        }
    } catch (e) {
        console.error('Error saving options position:', e);
        alert('Error saving position');
    }
}

async function loadOptionsPositions() {
    try {
        const response = await fetch(`${API_URL}/v2/positions?status=OPEN&asset_type=OPTION`);
        const data = await response.json();

        const positions = data.positions || [];
        renderOptionsPositions(positions);
        updateOptionsSummary(positions);

    } catch (e) {
        console.error('Error loading options positions:', e);
    }
}

function renderOptionsPositions(positions) {
    const container = document.getElementById('optionsPositionsList');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open options positions</p>';
        return;
    }

    const STRUCTURE_DISPLAY = {
        'call_debit_spread': 'Bull Call Spread',
        'put_debit_spread': 'Bear Put Spread',
        'call_credit_spread': 'Bear Call Spread',
        'put_credit_spread': 'Bull Put Spread',
        'long_call': 'Long Call',
        'long_put': 'Long Put',
        'iron_condor': 'Iron Condor',
        'straddle': 'Straddle',
        'strangle': 'Strangle',
        'stock': 'Stock',
        'custom': 'Custom'
    };

    container.innerHTML = positions.map(pos => {
        const dte = pos.dte;
        const dteClass = dte > 14 ? 'safe' : (dte > 7 ? 'warning' : 'danger');
        const pnl = pos.unrealized_pnl;
        const pnlClass = pnl > 0 ? 'positive' : (pnl < 0 ? 'negative' : '');

        // Build legs summary from unified legs field
        const legs = pos.legs || [];
        const legsSummary = legs.length > 0
            ? legs.map(leg =>
                `${leg.action} ${leg.quantity || 1}x ${leg.strike} ${leg.option_type} ${leg.expiration}`
              ).join(' | ')
            : `${pos.long_strike || ''}/${pos.short_strike || ''} ${pos.structure || ''}`;

        const pnlDisplay = pnl != null ? ((pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2)) : '--';
        const strategyName = STRUCTURE_DISPLAY[pos.structure] || pos.structure || '--';
        const directionClass = (pos.direction || '').toLowerCase();

        return `
            <div class="options-position-card" data-position-id="${pos.position_id}">
                <div class="position-header">
                    <div class="position-ticker">
                        <span class="ticker-symbol">${pos.ticker}</span>
                        <span class="strategy-badge ${directionClass}">${strategyName}</span>
                    </div>
                    <div class="position-dte ${dteClass}">
                        <span class="dte-value">${dte != null ? dte : '--'}</span>
                        <span class="dte-label">DTE</span>
                    </div>
                </div>
                <div class="position-legs">
                    <span class="legs-summary">${legsSummary}</span>
                </div>
                <div class="position-metrics">
                    <div class="metric">
                        <span class="metric-label">Entry</span>
                        <span class="metric-value">${pos.entry_price != null ? '$' + pos.entry_price.toFixed(2) : '--'}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">P&L</span>
                        <span class="metric-value ${pnlClass}">${pnlDisplay}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Delta</span>
                        <span class="metric-value">--</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Theta</span>
                        <span class="metric-value">--/day</span>
                    </div>
                </div>
                ${pos.notes ? `<div class="position-thesis">"${pos.notes}"</div>` : ''}
                <div class="position-actions">
                    <button class="position-btn" onclick="viewPositionDetails('${pos.position_id}')">Details</button>
                    <button class="position-btn" onclick="closeOptionsPosition('${pos.position_id}')">Close</button>
                </div>
            </div>
        `;
    }).join('');
}

function updateOptionsSummary(positions) {
    const countEl = document.getElementById('optionsCount');
    const pnlEl = document.getElementById('optionsTotalPnl');
    const deltaEl = document.getElementById('optionsNetDelta');
    const thetaEl = document.getElementById('optionsDailyTheta');

    if (countEl) countEl.textContent = positions.length;

    let totalPnl = 0;

    positions.forEach(pos => {
        if (pos.unrealized_pnl != null) {
            totalPnl += pos.unrealized_pnl;
        }
    });

    if (pnlEl) {
        pnlEl.textContent = '$' + (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(2);
        pnlEl.className = 'stat-value ' + (totalPnl >= 0 ? 'positive' : 'negative');
    }

    if (deltaEl) deltaEl.textContent = '--';
    if (thetaEl) thetaEl.textContent = '--';
}

async function viewPositionDetails(positionId) {
    try {
        const response = await fetch(`${API_URL}/v2/positions/${positionId}`);
        const data = await response.json();
        console.log('Position details:', data);
        // Could open a detail modal here
    } catch (e) {
        console.error('Error fetching position details:', e);
    }
}

async function closeOptionsPosition(positionId) {
    const exitPrice = prompt('Enter exit price per contract (e.g. 0.50):');
    if (exitPrice === null) return;

    const outcome = prompt('Outcome? (WIN, LOSS, BREAKEVEN)');

    try {
        const response = await fetch(`${API_URL}/v2/positions/${positionId}/close`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                exit_price: parseFloat(exitPrice),
                notes: outcome ? `Outcome: ${outcome.toUpperCase()}` : undefined,
                trade_outcome: outcome ? outcome.toUpperCase() : undefined
            })
        });

        const data = await response.json();

        if (response.ok) {
            loadOptionsPositions();
            const pnl = data.position?.realized_pnl || data.realized_pnl;
            console.log(`Position closed${pnl != null ? ` - P&L: $${pnl.toFixed(2)}` : ''}`);
        }
    } catch (e) {
        console.error('Error closing position:', e);
    }
}

// Make functions globally available
window.removeLeg = removeLeg;
window.viewPositionDetails = viewPositionDetails;
window.closeOptionsPosition = closeOptionsPosition;

// Initialize options tab on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initOptionsTab, 1600);
});





