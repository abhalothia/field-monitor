(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var fortuneMapUrl = "/api/v1/fortune-map";
  var allocationCalendarUrl = "/api/v1/allocations/";
  var dataLanesUrl = "/api/v1/data-lanes";
  var operatingProfileUrl = "/api/v1/operating-profile";
  var pilotReadinessUrl = "/api/v1/pilot/readiness";
  var managerSessionStatusUrl = "/api/v1/manager-session/status";
  var managerSessionLoginUrl = "/api/v1/manager-session/login";
  var managerSessionLogoutUrl = "/api/v1/manager-session/logout";
  var trackwickMetricsUrl = "/api/v1/trackwick/metrics";
  var trackwickHealthUrl = "/api/v1/trackwick/health";
  var trackwickRefreshUrl = "/api/v1/trackwick/refresh";
  var currentRuntime = null;
  var currentPortfolio = null;
  var currentProgramme = null;
  var currentFortuneMap = null;
  var currentView = "home";
  var currentOperatingUnitName = "";
  var currentFarmView = "map";
  var currentFarmerView = "cards";
  var currentWorkerView = "cards";
  var currentInboxMode = "priority";
  var connectedAllocationId = null;
  var leafletMaps = {};
  var sampleMode = false;
  var inboxOwnerId = null;
  var allocationCalendars = {};
  var focusedAllocationId = null;
  var allocationCalendarRequest = 0;
  var pendingAction = null;
  var focusExceptionId = null;
  var focusTargetView = "farms";
  var managerSessionAuthenticated = false;
  var localeStorageKey = "ffl.manager.interface-locale";
  var interfaceLocale = window.localStorage.getItem(localeStorageKey) === "hi" ? "hi" : "en";
  var copy = {
    en: {
      navHome: "Home", navFarms: "Farms", navFarmers: "Farmers", navWorkers: "Field workers", navInbox: "Inbox", navSettings: "Settings",
      refresh: "Refresh", pageTitle: "Home.", fieldPulse: "Daily direction", lastUpdate: "Last update", from: "From",
      sampleView: "", fortuneRice: "Fortune Rice", fortunePaddy: "Fortune paddy", indiaTime: "India Standard Time", fortuneNetwork: "Fortune network",
      localContext: "Local operating context", visitsFiled: "Visits filed", farmersOverdue: "Farmers overdue", highRiskIssues: "High-risk issues",
      supplyAtRisk: "Supply at risk", complianceGaps: "Compliance gaps", cropInterventions: "Crop interventions",
      purchaseDataUnavailable: "Purchase data not connected", pesticideProofUnavailable: "Pesticide and proof data not connected",
      farmersAtRisk: "farmers at risk",
      pesticideReviewCue: "{count} pesticide review cue", pesticideReviewCues: "{count} pesticide review cues", pesticideReviewOnly: "Review cues, not a compliance verdict",
      activeIntervention: "active intervention", activeInterventions: "active interventions",
      verifiedFarms: "Where verified farms are.", reviewedRecord: "Reviewed operating record", verifiedFields: "Verified fields",
      map: "Map", cards: "Cards", table: "Table", all: "All", field: "Field", crop: "Crop", variety: "Variety", status: "Status",
      reviewedPeople: "Reviewed people", farmer: "Farmer", farmerPlural: "Farmers", fieldWorker: "Field worker", fieldWorkerPlural: "Field workers",
      role: "Role", scope: "Scope", openWorkLabel: "Open work", decisionQueue: "Decision queue", priority: "Priority", decision: "Decision", owner: "Owner", dueLabel: "Due", inbox: "Inbox",
      oneThing: "One thing", managerAccess: "Manager access", sampleLocation: "Dargava · Gabhana · Aligarh", sampleGeometry: "Dargava · Gabhana · Aligarh",
      sampleWeather: "31°C · partly cloudy", sampleWeatherNote: "Dargava, Gabhana", hectare: "ha", openAction: "open action", openActions: "open actions", fieldCount: "field", fieldCountPlural: "fields",
      location: "Location", cropPlan: "Crop plan", area: "Area", risk: "Risk", issue: "Issue", visitToday: "visit today", visitsToday: "visits today",
      sampleFarm: "Jewar Model Farm · North Block", sampleFarmName: "Jewar Model Farm", sampleField: "North Block", sampleCrop: "Pusa Basmati 1121", sampleFarmerTrait: "Contract grower", sampleWorkerTrait: "Field operator", sampleLocationShort: "Dargava, Aligarh",
      reading: "reading", attention: "attention", reported: "reported", planned: "planned", verified: "verified", high: "high", moderate: "moderate", low: "low", critical: "critical",
      grower: "grower", fieldOperator: "field operator", stemBorer: "stem borer", leafFolder: "leaf folder",
      loading: "loading", today: "today", filedToday: "filed today", farmersNeedVisit: "farmers need a visit", highCriticalSevenDays: "high / critical · 7 days", notScheduled: "Not scheduled", notVisited: "never visited", reachedFourteenDays: "reached in 14 days", workerNoFile: "active officers did not file",
      coverageLoading: "Coverage is loading.", coverageUnavailable: "Coverage is unavailable.", dailyFilingLoading: "Daily filing is loading.", dailyFilingUnavailable: "Daily filing is unavailable.",
      mapUnavailable: "Map unavailable", noReviewedGeometry: "No reviewed geometry", reviewedField: "reviewed field", reviewedFields: "reviewed fields",
      settingsTitle: "Settings.", settingsDetail: "Access and source boundaries.", homeDetail: "What needs to move today.", farmsDetail: "Ground truth from reviewed farm and field records.", farmersDetail: "Coverage context and reviewed farmer relationships.", workersDetail: "Daily activity and reviewed ownership.", inboxDetail: "Decisions, work, and follow-through.",
      todayTitle: "Home.", farmsTitle: "Farms.", farmersTitle: "Farmers.", workersTitle: "Field workers.", inboxTitle: "Inbox.",
      openFarms: "Open farms", openFarmers: "Open farmers", openInbox: "Open inbox", openSettings: "Open settings", ready: "Ready.",
      managerUnlocked: "Manager actions are unlocked briefly on this browser.", managerLocked: "Manager actions are locked on this browser.", lockActions: "Lock manager actions", unlockActions: "Unlock manager actions", unlocking: "Unlocking…", unlockPrivateActions: "Unlock private actions", managerSecret: "Manager secret", managerSecretHelp: "Use the separately configured manager secret. It is sent only to this server and is never saved in the browser.", managerExpiry: "Manager access expires automatically.",
      directionLoadingTitle: "Reading the operation.", directionLoadingNote: "The field picture is loading.", dailyActivityLoading: "Daily activity loading", coverageLoadingShort: "Coverage loading", openWorkers: "Open field workers", awaitingSignal: "Awaiting field signal",
      coverageRiskTitle: "Field coverage is the supply risk.", coverageRiskNote: "{filed} visits were filed by {filing} of {active} field workers. Missing visits leave crop, purchase, and proof uncertain.",
      cropInterventionTitle: "{issue} needs a verified field intervention.", cropInterventionNote: "{count} dated observations in the last {days} days. Send a response, then verify the field outcome.",
      coverageRepairTitle: "Farm coverage needs repair.",
      officersNoVisitTitle: "{count} officers filed no visit today.", officersNoVisitNote: "{filed} visits were filed by {filing} of {active} active officers. Start with the coverage gap, then follow up with the field team.", officersFiled: "{filing} / {active} officers filed", farmersOverdueMetric: "{count} farmers overdue", reviewWorkerFollowUp: "Review worker follow-up",
      urgentIssueTitle: "{issue} is the lead field signal.", urgentIssueNote: "{count} dated observations in the last {days} days. Detection shows where to look, not a diagnosis or prevalence rate.", reviewDecisionQueue: "Review the decision queue", visitsFiledMetric: "{count} visits filed today", neverVisitedMetric: "{count} never visited",
      farmerOverdueTitle: "{count} farmers are overdue for a visit.", farmerCoverageCurrent: "Farmer coverage is current.", farmerOverdueNote: "Start with the farmer groups carrying the largest overdue gap. Never visited remains a separate acquisition and record-quality gap.", noOverdueNote: "No overdue visit gap is reported in the published farmer aggregate.", reviewFarmerCoverage: "Review farmer coverage",
      priorityDecision: "{count} priority decision, most urgent first.", priorityDecisions: "{count} priority decisions, most urgent first.", allDecisions: "{count} reviewed decisions and open work items.", noDecision: "No decision needs attention right now.", nothingWaiting: "Nothing is waiting for a manager decision.", sampleReviewIssue: "Review stem borer cluster", sampleCheckIssue: "Check stem borer cluster",
      viewRelatedDecisions: "View related decisions", showAllDecisions: "Show all decisions", decisionsForField: "Decisions for {field}",
      openFieldWork: "Open field workers", today: "Today", openWork: "Open work", awaitingReview: "Awaiting review",
      currentFields: "Current fields", work: "Work", selectedSignal: "Selected signal", review: "Review",
      priority: "Priority", riskAction: "Risk & action", learning: "Learning", trialsPlaybooks: "Trials & playbooks",
      operatingProfile: "Operating profile", coverage: "Coverage", interface: "Interface", language: "Language",
      languageHelp: "Choose Hindi or English for the interface. Farm records remain exactly as entered.",
      dataConnections: "Data connections", fiveDataLanes: "Five data lanes",
      lanesIntro: "What is usable now, what is missing, and the next safe move.", nextMove: "Next move",
      fieldAsk: "Field ask", fieldProofRequired: "field proof required", fieldUpdateRequested: "field update requested",
      noFieldPerson: "No field person assigned", due: "due", fieldAskNeedsReview: "needs manager review",
      fieldAskReady: "is reviewed; delivery stays independently gated", awaitingFieldAnswer: "Awaiting a reviewable field answer from",
      checkDelivery: "Check delivery eligibility or cancel and reissue it. Do not assume an answer.",
      reviewFieldAnswer: "Review any response and retained proof. The linked work stays open until a human closes it.",
      openFieldAsks: "Open field asks"
    },
    hi: {
      navHome: "मुख्य", navFarms: "खेत", navFarmers: "किसान", navWorkers: "फील्ड टीम", navInbox: "इनबॉक्स", navSettings: "सेटिंग्स",
      refresh: "ताज़ा करें", pageTitle: "मुख्य।", fieldPulse: "आज की दिशा", lastUpdate: "आख़िरी अपडेट", from: "किससे",
      sampleView: "", fortuneRice: "फॉर्च्यून राइस", fortunePaddy: "फॉर्च्यून धान", indiaTime: "भारतीय मानक समय", fortuneNetwork: "फॉर्च्यून नेटवर्क",
      localContext: "स्थानीय परिचालन संदर्भ", visitsFiled: "दर्ज की गई मुलाक़ातें", farmersOverdue: "मुलाक़ात के लिए बाकी किसान", highRiskIssues: "उच्च जोखिम के मुद्दे",
      supplyAtRisk: "जोखिम में आपूर्ति", complianceGaps: "अनुपालन की कमी", cropInterventions: "फसल हस्तक्षेप",
      purchaseDataUnavailable: "खरीद डेटा नहीं जुड़ा है", pesticideProofUnavailable: "कीटनाशक और प्रमाण डेटा नहीं जुड़ा है",
      farmersAtRisk: "किसान जोखिम में हैं",
      pesticideReviewCue: "{count} कीटनाशक समीक्षा संकेत", pesticideReviewCues: "{count} कीटनाशक समीक्षा संकेत", pesticideReviewOnly: "समीक्षा संकेत हैं, अनुपालन का निर्णय नहीं",
      activeIntervention: "सक्रिय हस्तक्षेप", activeInterventions: "सक्रिय हस्तक्षेप",
      verifiedFarms: "सत्यापित खेत कहाँ हैं", reviewedRecord: "समीक्षित परिचालन रिकॉर्ड", verifiedFields: "सत्यापित खेत",
      map: "नक्शा", cards: "कार्ड", table: "तालिका", all: "सभी", field: "खेत", crop: "फसल", variety: "किस्म", status: "स्थिति",
      reviewedPeople: "समीक्षित लोग", farmer: "किसान", farmerPlural: "किसान", fieldWorker: "फील्ड कर्मी", fieldWorkerPlural: "फील्ड कर्मी",
      role: "भूमिका", scope: "दायरा", openWorkLabel: "खुला काम", decisionQueue: "निर्णय सूची", priority: "प्राथमिकता", decision: "निर्णय", owner: "जिम्मेदार", dueLabel: "समय", inbox: "इनबॉक्स",
      oneThing: "एक काम", managerAccess: "प्रबंधक पहुँच", sampleLocation: "दरगावा · गभाना · अलीगढ़", sampleGeometry: "दरगावा · गभाना · अलीगढ़",
      sampleWeather: "31°C · आंशिक बादल", sampleWeatherNote: "दरगावा, गभाना", hectare: "हेक्टेयर", openAction: "खुला काम", openActions: "खुले काम", fieldCount: "खेत", fieldCountPlural: "खेत",
      location: "स्थान", cropPlan: "फसल योजना", area: "क्षेत्र", risk: "जोखिम", issue: "मुद्दा", visitToday: "आज की मुलाक़ात", visitsToday: "आज की मुलाक़ातें",
      sampleFarm: "जेवर मॉडल फ़ार्म · उत्तर खंड", sampleFarmName: "जेवर मॉडल फ़ार्म", sampleField: "उत्तर खंड", sampleCrop: "पूसा बासमती 1121", sampleFarmerTrait: "अनुबंधित किसान", sampleWorkerTrait: "फील्ड कर्मी", sampleLocationShort: "दरगावा, अलीगढ़",
      reading: "पढ़ा जा रहा है", attention: "ध्यान", reported: "दर्ज", planned: "योजित", verified: "सत्यापित", high: "उच्च", moderate: "मध्यम", low: "कम", critical: "अति गंभीर",
      grower: "किसान", fieldOperator: "फील्ड कर्मी", stemBorer: "तना छेदक", leafFolder: "पत्ता लपेटक",
      loading: "लोड हो रहा है", today: "आज", filedToday: "आज दर्ज", farmersNeedVisit: "किसानों की मुलाक़ात बाकी", highCriticalSevenDays: "उच्च / अति गंभीर · 7 दिन", notScheduled: "निर्धारित नहीं", notVisited: "कभी मुलाक़ात नहीं हुई", reachedFourteenDays: "14 दिन में पहुँचे", workerNoFile: "सक्रिय कर्मियों ने दर्ज नहीं किया",
      coverageLoading: "कवरेज लोड हो रहा है।", coverageUnavailable: "कवरेज उपलब्ध नहीं है।", dailyFilingLoading: "दैनिक दर्ज करना लोड हो रहा है।", dailyFilingUnavailable: "दैनिक दर्ज करना उपलब्ध नहीं है।",
      mapUnavailable: "नक्शा उपलब्ध नहीं है", noReviewedGeometry: "कोई सत्यापित ज्यामिति नहीं", reviewedField: "सत्यापित खेत", reviewedFields: "सत्यापित खेत",
      settingsTitle: "सेटिंग्स।", settingsDetail: "पहुँच और स्रोत सीमाएँ।", homeDetail: "आज क्या आगे बढ़ाना है।", farmsDetail: "समीक्षित खेत और फील्ड रिकॉर्ड से वास्तविक स्थिति।", farmersDetail: "कवरेज और समीक्षित किसान संबंध।", workersDetail: "दैनिक गतिविधि और जिम्मेदारी।", inboxDetail: "निर्णय, काम और अनुपालन।",
      todayTitle: "मुख्य।", farmsTitle: "खेत।", farmersTitle: "किसान।", workersTitle: "फील्ड कर्मी।", inboxTitle: "इनबॉक्स।",
      openFarms: "खेत खोलें", openFarmers: "किसान खोलें", openInbox: "इनबॉक्स खोलें", openSettings: "सेटिंग्स खोलें", ready: "तैयार।",
      managerUnlocked: "इस ब्राउज़र में प्रबंधक कार्रवाई कुछ समय के लिए खुली है।", managerLocked: "इस ब्राउज़र में प्रबंधक कार्रवाई बंद है।", lockActions: "प्रबंधक कार्रवाई बंद करें", unlockActions: "प्रबंधक कार्रवाई खोलें", unlocking: "खोला जा रहा है…", unlockPrivateActions: "निजी कार्रवाई खोलें", managerSecret: "प्रबंधक पासवर्ड", managerSecretHelp: "अलग से तय प्रबंधक पासवर्ड इस्तेमाल करें। यह केवल इस सर्वर को भेजा जाता है और ब्राउज़र में सहेजा नहीं जाता।", managerExpiry: "प्रबंधक पहुँच अपने-आप समाप्त हो जाती है।",
      directionLoadingTitle: "परिचालन स्थिति पढ़ी जा रही है।", directionLoadingNote: "खेतों की स्थिति लोड हो रही है।", dailyActivityLoading: "दैनिक गतिविधि लोड हो रही है", coverageLoadingShort: "कवरेज लोड हो रहा है", openWorkers: "फील्ड कर्मी खोलें", awaitingSignal: "फील्ड संकेत की प्रतीक्षा",
      coverageRiskTitle: "फील्ड कवरेज ही आपूर्ति जोखिम है।", coverageRiskNote: "{active} फील्ड कर्मियों में से {filing} ने {filed} मुलाक़ातें दर्ज कीं। अधूरी मुलाक़ात से फसल, खरीद और प्रमाण अनिश्चित रहते हैं।",
      cropInterventionTitle: "{issue} के लिए सत्यापित फील्ड हस्तक्षेप चाहिए।", cropInterventionNote: "पिछले {days} दिनों में {count} दर्ज अवलोकन। प्रतिक्रिया भेजें, फिर फील्ड परिणाम सत्यापित करें।",
      coverageRepairTitle: "फार्म कवरेज ठीक करना है।",
      officersNoVisitTitle: "{count} कर्मियों ने आज कोई मुलाक़ात दर्ज नहीं की।", officersNoVisitNote: "{active} सक्रिय कर्मियों में से {filing} ने {filed} मुलाक़ातें दर्ज कीं। पहले कवरेज की कमी देखें, फिर फील्ड टीम से संपर्क करें।", officersFiled: "{filing} / {active} कर्मियों ने दर्ज किया", farmersOverdueMetric: "{count} किसानों की मुलाक़ात बाकी", reviewWorkerFollowUp: "कर्मियों की फॉलो-अप सूची देखें",
      urgentIssueTitle: "{issue} मुख्य फील्ड संकेत है।", urgentIssueNote: "पिछले {days} दिनों में {count} दर्ज अवलोकन। यह बताता है कि कहाँ देखना है, निदान या प्रसार दर नहीं।", reviewDecisionQueue: "निर्णय सूची देखें", visitsFiledMetric: "आज {count} मुलाक़ातें दर्ज", neverVisitedMetric: "{count} से कभी मुलाक़ात नहीं हुई",
      farmerOverdueTitle: "{count} किसानों की मुलाक़ात बाकी है।", farmerCoverageCurrent: "किसान कवरेज वर्तमान है।", farmerOverdueNote: "सबसे अधिक बाकी मुलाक़ात वाले किसान समूहों से शुरुआत करें। कभी न मिले किसान अलग कवरेज और रिकॉर्ड गुणवत्ता की कमी हैं।", noOverdueNote: "प्रकाशित किसान आँकड़ों में कोई बाकी मुलाक़ात नहीं है।", reviewFarmerCoverage: "किसान कवरेज देखें",
      priorityDecision: "{count} प्राथमिक निर्णय, सबसे जरूरी पहले।", priorityDecisions: "{count} प्राथमिक निर्णय, सबसे जरूरी पहले।", allDecisions: "{count} समीक्षित निर्णय और खुले काम।", noDecision: "अभी किसी निर्णय पर ध्यान नहीं चाहिए।", nothingWaiting: "प्रबंधक के निर्णय की कोई प्रतीक्षा नहीं है।", sampleReviewIssue: "तना छेदक समूह की समीक्षा", sampleCheckIssue: "तना छेदक समूह जाँचें",
      viewRelatedDecisions: "संबंधित निर्णय देखें", showAllDecisions: "सभी निर्णय देखें", decisionsForField: "{field} के निर्णय",
      openFieldWork: "फील्ड टीम खोलें", today: "आज", openWork: "खुला काम", awaitingReview: "समीक्षा के लिए",
      currentFields: "मौजूदा खेत", work: "काम", selectedSignal: "चुना हुआ संकेत", review: "समीक्षा",
      priority: "प्राथमिकता", riskAction: "जोखिम और अगला काम", learning: "सीख", trialsPlaybooks: "परीक्षण और तरीके",
      operatingProfile: "ऑपरेटिंग प्रोफ़ाइल", coverage: "कवरेज", interface: "इंटरफ़ेस", language: "भाषा",
      languageHelp: "इंटरफ़ेस के लिए हिंदी या अंग्रेज़ी चुनें। खेत के रिकॉर्ड जैसे दर्ज किए गए हैं वैसे ही रहेंगे।",
      dataConnections: "डेटा कनेक्शन", fiveDataLanes: "पांच डेटा लेन",
      lanesIntro: "क्या उपयोगी है, क्या नहीं है, और अगला सुरक्षित कदम।", nextMove: "अगला कदम",
      fieldAsk: "खेत की जानकारी", fieldProofRequired: "खेत का प्रमाण चाहिए", fieldUpdateRequested: "खेत का अपडेट चाहिए",
      noFieldPerson: "कोई फील्ड व्यक्ति तय नहीं", due: "समय", fieldAskNeedsReview: "को प्रबंधक की समीक्षा चाहिए",
      fieldAskReady: "की समीक्षा हो चुकी है; भेजना अलग से स्वीकृत होगा", awaitingFieldAnswer: "समीक्षा योग्य उत्तर की प्रतीक्षा",
      checkDelivery: "भेजने की पात्रता जाँचें या इसे रद्द करके फिर से जारी करें। उत्तर मान कर न चलें।",
      reviewFieldAnswer: "किसी भी उत्तर और सुरक्षित प्रमाण की समीक्षा करें। मानव बंद होने तक जुड़ा काम खुला रहता है।",
      openFieldAsks: "खेत की जानकारी खोलें"
    }
  };

  function element(id) {
    return document.getElementById(id);
  }

  function text(value) {
    return value === null || value === undefined || value === "" ? "Not assigned" : String(value);
  }

  function t(key) {
    return (copy[interfaceLocale] && copy[interfaceLocale][key]) || (copy.en[key] || key);
  }

  function message(key, values) {
    return t(key).replace(/\{(\w+)\}/g, function (_match, name) {
      return values && values[name] !== undefined ? values[name] : "";
    });
  }

  function applyLanguage() {
    document.documentElement.lang = interfaceLocale === "hi" ? "hi" : "en";
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    element("language-toggle").textContent = interfaceLocale === "hi" ? "EN" : "हिं";
    element("language-toggle").setAttribute(
      "aria-label", interfaceLocale === "hi" ? "Switch interface language to English" : "इंटरफ़ेस भाषा हिंदी में बदलें"
    );
    Array.prototype.forEach.call(document.querySelectorAll("[data-locale]"), function (button) {
      var selected = button.getAttribute("data-locale") === interfaceLocale;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    renderPageIntro();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function setLocale(locale) {
    interfaceLocale = locale === "hi" ? "hi" : "en";
    window.localStorage.setItem(localeStorageKey, interfaceLocale);
    applyLanguage();
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderPeople(currentRuntime);
    }
    if (currentFortuneMap) {
      renderFortuneMap(currentFortuneMap);
    }
    if (currentPortfolio) {
      renderPortfolio(currentPortfolio);
    }
    if (currentProgramme) {
      renderProgramme(currentProgramme.metrics, currentProgramme.health);
    }
    renderTodayClock();
  }

  function setManagerSessionFeedback(message) {
    var feedback = element("manager-session-feedback");
    feedback.textContent = message || "";
    feedback.hidden = !message;
  }

  function renderManagerSessionStatus(session) {
    managerSessionAuthenticated = Boolean(session && session.authenticated === true);
    var status = element("manager-session-status");
    var action = element("manager-session-action");
    status.classList.toggle("is-unlocked", managerSessionAuthenticated);
    status.textContent = managerSessionAuthenticated ?
      t("managerUnlocked") : t("managerLocked");
    action.textContent = managerSessionAuthenticated ? t("lockActions") : t("unlockActions");
  }

  function loadManagerSessionStatus() {
    return fetch(managerSessionStatusUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Manager status is unavailable.");
        }
        return response.json();
      })
      .then(renderManagerSessionStatus)
      .catch(function () {
        renderManagerSessionStatus({ authenticated: false });
      });
  }

  function openManagerSessionDialog() {
    setManagerSessionFeedback("");
    var dialog = element("manager-session-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
    element("manager-session-secret").focus();
  }

  function submitManagerSession(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form.reportValidity()) {
      return;
    }
    setManagerSessionFeedback("");
    var submit = element("submit-manager-session");
    submit.disabled = true;
    submit.textContent = t("unlocking");
    // The secret exists only in the form/request body.  It is deliberately
    // never written to localStorage, sessionStorage, a URL, or an API header.
    fetch(managerSessionLoginUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret: formValue(form, "secret") })
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.detail || "Manager access could not be unlocked.");
          }
          return body;
        });
      })
      .then(function () {
        form.reset();
        element("manager-session-dialog").close();
        return loadManagerSessionStatus();
      })
      .then(loadActionCentre)
      .catch(function (error) {
        form.reset();
        setManagerSessionFeedback(error.message || "Manager access could not be unlocked.");
      })
      .finally(function () {
        submit.disabled = false;
        submit.textContent = t("unlockActions");
      });
  }

  function toggleManagerSession() {
    if (!managerSessionAuthenticated) {
      openManagerSessionDialog();
      return;
    }
    element("manager-session-action").disabled = true;
    fetch(managerSessionLogoutUrl, { method: "POST", credentials: "same-origin" })
      .then(function () { return loadManagerSessionStatus(); })
      .then(loadActionCentre)
      .finally(function () {
        element("manager-session-action").disabled = false;
      });
  }

  function setSampleMode(enabled) {
    sampleMode = Boolean(enabled);
  }

  function sampleRuntime() {
    return {
      operating_unit: { name: "Fortune Rice" },
      allocations: [{
        id: "sample-north-block", farm_name: "Jewar Model Farm", operational_block_name: "North Block",
        crop_name: "Pusa Basmati 1121", cultivar: "1121", area_hectares: 2.5,
        location_label: "Dargava, Gabhana, Aligarh"
      }],
      people: [
        { id: "sample-asha", name: "Asha Devi", role: "grower", characteristics: ["Contract grower", "Pusa Basmati 1121", "2.5 ha"] },
        { id: "sample-ravi", name: "Ravi Kumar", role: "field_operator", characteristics: ["Field operator", "North Block", "1 urgent action"] }
      ],
      work_items: [{ id: "sample-visit", allocation_id: "sample-north-block", title: "Check stem borer cluster", owner_id: "sample-ravi", due_at: new Date().toISOString(), status: "planned" }],
      exceptions: [],
      latest_field_update: null,
      person_operating_relationships: {
        availability: "available",
        items: [
          { person_id: "sample-asha", role: "grower", scope_name: "North Block" },
          { person_id: "sample-ravi", role: "field operator", scope_name: "North Block" }
        ]
      }
    };
  }

  function sampleProgramme() {
    return {
      coverage: { taken_kit: 2592, visited: 1941, recent: 1585, overdue: 1007, never_visited: 651 },
      visits: { filed_on_reporting_day: 5, filing_officers: 2, active_officers: 24, active_officers_without_filed_visit: 22 },
      issues: {
        window_days: 7,
        observation_count: 545,
        by_issue: [
          { issue_code: "stem borer", count: 215, highest_severity: "high" },
          { issue_code: "leaf folder", count: 265, highest_severity: "moderate" }
        ]
      },
      freshness: { status: "available", age_hours: 1 }
    };
  }

  function samplePortfolio() {
    return {
      risk_action_ledger: {
        items: [{
          severity: "high", action: "review field signal", entity: { type: "exception_record", id: "sample-stem-borer" },
          status: "reported", title: "Review stem borer cluster", allocation_id: "sample-north-block",
          owner_id: "sample-ravi", observed_at: new Date().toISOString()
        }]
      }
    };
  }

  function sampleMap() {
    return {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Point", coordinates: [77.7853488, 28.1052221] },
        properties: {
          plot_label: "Jewar Model Farm · North Block", crop_name: "Pusa Basmati 1121", cultivar: "1121",
          area_hectares: 2.5, location_label: "Dargava, Gabhana, Aligarh", location_precision: "sample",
          record_kind: "farm", record_id: "sample-north-block"
        }
      }]
    };
  }

  function renderSampleWeather() {
    element("weather-state").textContent = t("sampleWeather");
    element("weather-note").textContent = t("sampleWeatherNote");
  }

  function formatTime(value) {
    if (!value) {
      return t("notScheduled");
    }
    var date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString(interfaceLocale === "hi" ? "hi-IN" : "en-IN");
  }

  function formatCount(value) {
    var count = Number(value);
    if (!isFinite(count) || count < 0) {
      return "—";
    }
    return Math.round(count).toLocaleString(interfaceLocale === "hi" ? "hi-IN" : "en-IN");
  }

  function formatAgeHours(value) {
    var hours = Number(value);
    if (!isFinite(hours) || hours < 0) {
      return "No published timestamp";
    }
    if (hours < 1) {
      return "Under 1 hour";
    }
    return Math.round(hours) + (Math.round(hours) === 1 ? " hour" : " hours");
  }

  function programmeFact(label, value) {
    return "<div><dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(formatCount(value)) + "</dd></div>";
  }

  function workerFact(label, value) {
    return "<div><dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(value) + "</dd></div>";
  }

  function renderTodayClock() {
    var now = new Date();
    var locale = interfaceLocale === "hi" ? "hi-IN" : "en-IN";
    element("today-date").textContent = now.toLocaleDateString(locale, {
      weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata"
    });
    element("today-time").textContent = now.toLocaleTimeString(locale, {
      hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata"
    });
  }

  function renderWeatherContext(snapshot) {
    if (sampleMode) {
      renderSampleWeather();
      return;
    }
    var lanes = snapshot && Array.isArray(snapshot.lanes) ? snapshot.lanes : [];
    var weather = lanes.filter(function (lane) { return lane.key === "weather"; })[0];
    if (!weather) {
      element("weather-state").textContent = t("loading");
      element("weather-note").textContent = "";
      return;
    }
    var ready = weather.status === "context_available";
    element("weather-state").textContent = ready ? weather.fact : t("loading");
    element("weather-note").textContent = "";
  }

  function renderWeatherUnavailable() {
    if (sampleMode) {
      renderSampleWeather();
      return;
    }
    element("weather-state").textContent = t("loading");
    element("weather-note").textContent = "";
  }

  function setHomeMetric(valueId, noteId, value, note) {
    element(valueId).textContent = value;
    element(noteId).textContent = note;
  }

  function renderHomeMetrics() {
    var metrics = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    var runtime = currentRuntime || {};
    var procurement = (metrics && metrics.procurement) || runtime.procurement || null;
    var supplyAtRisk = procurement && firstKnownNumber([
      procurement.farmers_at_risk, procurement.at_risk_farmers, procurement.at_risk_count
    ]);
    setHomeMetric(
      "home-supply-value", "home-supply-note",
      supplyAtRisk === null ? "—" : formatCount(supplyAtRisk),
      supplyAtRisk === null ? t("purchaseDataUnavailable") : t("farmersAtRisk")
    );
    var sourceFreshness = metrics && metrics.freshness ? metrics.freshness.status : "unavailable";
    var pesticides = sourceFreshness === "available" && metrics && metrics.pesticides ? metrics.pesticides : null;
    var pesticideEventCount = pesticides ? firstKnownNumber([pesticides.event_count]) : null;
    var complianceGaps = pesticides ? firstKnownNumber([pesticides.off_kit_review_cues]) : null;
    setHomeMetric(
      "home-compliance-value", "home-compliance-note",
      pesticideEventCount === null || complianceGaps === null ? "—" : formatCount(complianceGaps),
      pesticideEventCount === null || complianceGaps === null ? t("pesticideProofUnavailable") :
        (complianceGaps === 1 ? message("pesticideReviewCue", { count: formatCount(complianceGaps) }) :
          message("pesticideReviewCues", { count: formatCount(complianceGaps) })) + " · " + t("pesticideReviewOnly")
    );
    var interventions = openInterventionCount();
    setHomeMetric(
      "home-interventions-value", "home-interventions-note",
      interventions === null ? "—" : formatCount(interventions),
      interventions === null ? t("loading") : (interventions === 1 ? t("activeIntervention") : t("activeInterventions"))
    );
  }

  function firstKnownNumber(values) {
    for (var index = 0; index < values.length; index += 1) {
      if (values[index] === null || values[index] === undefined || values[index] === "") {
        continue;
      }
      var value = Number(values[index]);
      if (isFinite(value) && value >= 0) {
        return value;
      }
    }
    return null;
  }

  function openInterventionCount() {
    var ledger = currentPortfolio && currentPortfolio.risk_action_ledger;
    var items = listedItems(ledger);
    if (items.length) {
      return items.filter(function (item) {
        return ["resolved", "accepted", "completed", "cancelled", "closed"].indexOf(item.status) === -1;
      }).length;
    }
    if (!currentRuntime) {
      return null;
    }
    return (currentRuntime.work_items || []).filter(isOpenWork).length +
      (currentRuntime.exceptions || []).filter(isOpenException).length;
  }

  function renderWorkerActivity() {
    var metrics = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!metrics) {
      element("worker-boundary").textContent = "";
      element("worker-activity").textContent = managerSessionAuthenticated ?
        t("dailyFilingUnavailable") : t("dailyFilingLoading");
      renderHomeMetrics();
      return;
    }
    var visits = metrics.visits || {};
    var freshness = metrics.freshness || {};
    var active = Number(visits.active_officers) || 0;
    var filed = Number(visits.filed_on_reporting_day) || 0;
    var filing = Number(visits.filing_officers) || 0;
    var missing = Number(visits.active_officers_without_filed_visit) || 0;
    element("worker-boundary").textContent = "";
    element("worker-activity").textContent = formatCount(filed) + " " + t("filedToday") + " · " +
      formatCount(missing) + " " + t("workerNoFile");
    renderHomeMetrics();
  }

  function programmeWarningCopy(code) {
    if (code === "low_observation_confidence") {
      return "Observation confidence is low. Fewer detections do not mean risk has fallen.";
    }
    return "Review source limitation: " + readable(code) + ".";
  }

  function renderProgrammeLocked() {
    if (sampleMode) {
      renderProgramme(sampleProgramme(), { state: "sample" });
      return;
    }
    currentProgramme = null;
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = t("coverageLoading");
    renderWorkerActivity();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function renderProgrammeUnavailable() {
    if (sampleMode) {
      renderProgramme(sampleProgramme(), { state: "sample" });
      return;
    }
    currentProgramme = null;
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = t("coverageUnavailable");
    renderWorkerActivity();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function renderProgramme(metrics, health) {
    var coverage = metrics && metrics.coverage ? metrics.coverage : {};

    currentProgramme = { metrics: metrics || {}, health: health || {} };
    renderDailyDirection();
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = formatCount(coverage.overdue) + " " + t("farmersOverdue") + " · " +
      formatCount(coverage.never_visited) + " " + t("notVisited") + " · " + formatCount(coverage.recent) +
      " " + t("reachedFourteenDays");
    renderWorkerActivity();
    renderHomeMetrics();
  }

  function loadProgramme() {
    if (!managerSessionAuthenticated) {
      renderProgrammeLocked();
      return Promise.resolve();
    }
    return Promise.all([
      fetch(trackwickMetricsUrl, { credentials: "same-origin" }),
      fetch(trackwickHealthUrl, { credentials: "same-origin" })
    ])
      .then(function (responses) {
        if (!responses[0].ok || !responses[1].ok) {
          throw new Error("Programme context is unavailable.");
        }
        return Promise.all([responses[0].json(), responses[1].json()]);
      })
      .then(function (payloads) {
        renderProgramme(payloads[0], payloads[1]);
      })
      .catch(renderProgrammeUnavailable);
  }

  function isOpenException(exceptionRecord) {
    return ["resolved", "accepted_risk"].indexOf(exceptionRecord.status) === -1;
  }

  function isOpenWork(workItem) {
    return ["accepted", "completed", "cancelled"].indexOf(workItem.status) === -1;
  }

  function isOverdue(workItem) {
    return isOpenWork(workItem) && workItem.due_at && new Date(workItem.due_at).getTime() < Date.now();
  }

  function setHtml(id, markup) {
    element(id).innerHTML = markup;
  }

  function escapeHtml(value) {
    return text(value).replace(/[&<>'"]/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character];
    });
  }

  function readable(value) {
    var raw = text(value);
    var normalized = raw.toLowerCase().replace(/[\s/-]+/g, "_");
    var translated = {
      grower: "grower", field_operator: "fieldOperator", field_operator_: "fieldOperator",
      stem_borer: "stemBorer", leaf_folder: "leafFolder", reported: "reported", planned: "planned",
      high: "high", moderate: "moderate", low: "low", critical: "critical", attention: "attention",
      reading: "reading"
    }[normalized];
    return translated ? t(translated) : raw.replace(/_/g, " ");
  }

  function sampleText(value) {
    var raw = String(value || "");
    if (!sampleMode) {
      return raw;
    }
    var labels = {
      "Jewar Model Farm": "sampleFarmName",
      "North Block": "sampleField",
      "Jewar Model Farm · North Block": "sampleFarm",
      "Pusa Basmati 1121": "sampleCrop",
      "Dargava, Gabhana, Aligarh": "sampleGeometry",
      "Contract grower": "sampleFarmerTrait",
      "Field operator": "sampleWorkerTrait",
      "1 urgent action": "openAction",
      "Review stem borer cluster": "sampleReviewIssue",
      "Check stem borer cluster": "sampleCheckIssue"
    };
    return labels[raw] ? t(labels[raw]) : raw.replace("2.5 ha", "2.5 " + t("hectare"));
  }

  function fieldLabel(value) {
    return sampleText(value || t("field"));
  }

  function cropLabel(value) {
    return sampleText(value || t("crop"));
  }

  function areaLabel(value) {
    var area = Number(value);
    return isFinite(area) && area > 0 ? area + " " + t("hectare") : "—";
  }

  function listedItems(summary) {
    return summary && Array.isArray(summary.items) ? summary.items : [];
  }

  function safeSeverity(value) {
    return ["critical", "high", "medium", "low", "info"].indexOf(value) === -1 ? "medium" : value;
  }

  function formValue(form, name) {
    return String(new FormData(form).get(name) || "").trim();
  }

  function pageMeta(viewName) {
    var labels = {
      home: { title: t("todayTitle"), detail: sampleMode ? t("fortuneRice") + " · " + t("sampleLocationShort") : (currentOperatingUnitName || t("homeDetail")) },
      farms: { title: t("farmsTitle"), detail: t("farmsDetail") },
      farmers: { title: t("farmersTitle"), detail: t("farmersDetail") },
      workers: { title: t("workersTitle"), detail: t("workersDetail") },
      inbox: { title: t("inboxTitle"), detail: t("inboxDetail") },
      settings: { title: t("settingsTitle"), detail: t("settingsDetail") }
    };
    return labels[viewName] || labels.home;
  }

  function renderPageIntro() {
    var meta = pageMeta(currentView);
    var pageTitle = element("page-title");
    if (pageTitle) {
      pageTitle.textContent = meta.title;
    }
    element("operating-unit").textContent = meta.detail;
  }

  function showView(viewName) {
    currentView = viewName;
    var tabs = document.querySelectorAll(".command-tab");
    var views = document.querySelectorAll(".command-view");
    Array.prototype.forEach.call(tabs, function (tab) {
      var selected = tab.getAttribute("data-view") === viewName;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    Array.prototype.forEach.call(views, function (view) {
      var selected = view.id === "panel-" + viewName;
      view.hidden = !selected;
      view.classList.toggle("is-active", selected);
    });
    renderPageIntro();
    window.setTimeout(function () {
      if (viewName === "home" || (viewName === "farms" && currentFarmView === "map")) {
        Object.keys(leafletMaps).forEach(function (id) { leafletMaps[id].invalidateSize(); });
      }
    }, 0);
  }

  function updateRecordRoute(kind, id) {
    var url = new URL(window.location.href);
    if (kind && id) {
      url.searchParams.set("record", kind + ":" + id);
    } else {
      url.searchParams.delete("record");
    }
    if (connectedAllocationId) {
      url.searchParams.set("field", connectedAllocationId);
    } else {
      url.searchParams.delete("field");
    }
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }

  function routeRecord() {
    var url = new URL(window.location.href);
    var raw = url.searchParams.get("record") || "";
    var separator = raw.indexOf(":");
    return separator > 0 ? { kind: raw.slice(0, separator), id: raw.slice(separator + 1) } : null;
  }

  function connectFarm(allocationId) {
    if (!allocationFor(allocationId)) {
      return;
    }
    connectedAllocationId = allocationId;
    renderCards(currentRuntime);
    renderRiskLedger();
  }

  function restoreConnectedRecord() {
    var url = new URL(window.location.href);
    var fieldId = url.searchParams.get("field");
    connectedAllocationId = fieldId && allocationFor(fieldId) ? fieldId : null;
    if (connectedAllocationId) {
      renderCards(currentRuntime);
      renderRiskLedger();
    }
    var record = routeRecord();
    if (!record || ["farm", "farmer", "worker"].indexOf(record.kind) === -1) {
      return;
    }
    if (record.kind === "farm") {
      connectFarm(record.id);
      updateRecordRoute(record.kind, record.id);
      showView("farms");
    } else {
      showView(record.kind === "farmer" ? "farmers" : "workers");
    }
    openRecordDialog(record.kind, record.id, false);
  }

  function setDirectoryView(kind, value) {
    var settings = {
      farm: { value: value, cards: "farm-cards-view", table: "farm-table-view", map: "farm-map-view", selector: "[data-farm-view]" },
      farmer: { value: value, cards: "farmer-cards-view", table: "farmer-table-view", selector: "[data-farmer-view]" },
      worker: { value: value, cards: "worker-cards-view", table: "worker-table-view", selector: "[data-worker-view]" }
    };
    var setting = settings[kind];
    if (!setting) {
      return;
    }
    if (kind === "farm") { currentFarmView = value; }
    if (kind === "farmer") { currentFarmerView = value; }
    if (kind === "worker") { currentWorkerView = value; }
    ["cards", "table", "map"].forEach(function (view) {
      if (!setting[view]) {
        return;
      }
      element(setting[view]).hidden = view !== value;
    });
    Array.prototype.forEach.call(document.querySelectorAll(setting.selector), function (button) {
      var selected = button.getAttribute(kind === "farm" ? "data-farm-view" : (kind === "farmer" ? "data-farmer-view" : "data-worker-view")) === value;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    if (kind === "farm" && value === "map" && leafletMaps["farm-map-canvas"]) {
      window.setTimeout(function () { leafletMaps["farm-map-canvas"].invalidateSize(); }, 0);
    }
  }

  function setInboxMode(mode) {
    currentInboxMode = mode === "all" ? "all" : "priority";
    Array.prototype.forEach.call(document.querySelectorAll("[data-inbox-mode]"), function (button) {
      var selected = button.getAttribute("data-inbox-mode") === currentInboxMode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    renderRiskLedger();
  }

  function activateView(event) {
    showView(event.currentTarget.getAttribute("data-view"));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function moveTab(event) {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".command-tab"));
    var currentIndex = tabs.indexOf(event.currentTarget);
    if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(event.key) === -1) {
      return;
    }
    event.preventDefault();
    var nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[nextIndex].focus();
    showView(tabs[nextIndex].getAttribute("data-view"));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderPortfolioUnavailable() {
    if (sampleMode) {
      currentPortfolio = samplePortfolio();
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    currentPortfolio = null;
    if (currentRuntime) {
      renderDailyDirection();
    }
    element("portfolio-status").textContent = "Actions are unavailable. Home is still usable.";
    element("inbox-summary").textContent = "The decision queue is unavailable right now.";
    setHtml("portfolio-ledger", '<tr><td colspan="6" class="table-empty">Risk and action context is unavailable right now.</td></tr>');
    renderHomeMetrics();
  }

  function inboxRows() {
    var ledger = currentPortfolio ? listedItems(currentPortfolio.risk_action_ledger) : [];
    var rows = ledger.map(function (item) {
      return {
        key: (item.entity && item.entity.type ? item.entity.type : "decision") + ":" + (item.entity && item.entity.id ? item.entity.id : item.title),
        severity: safeSeverity(item.severity), title: item.title, allocationId: item.allocation_id,
        ownerId: item.owner_id, dueAt: item.due_at || item.observed_at, status: item.status,
        action: item.action
      };
    });
    if (currentInboxMode === "all" && currentRuntime) {
      var known = {};
      rows.forEach(function (row) { known[row.key] = true; });
      (currentRuntime.exceptions || []).filter(isOpenException).forEach(function (item) {
        var exceptionKey = "exception_record:" + item.id;
        if (!known[exceptionKey]) {
          rows.push({ key: exceptionKey, severity: safeSeverity(item.severity), title: item.title, allocationId: item.allocation_id,
            ownerId: item.owner_id, dueAt: item.observed_at, status: item.status, action: "review exception" });
        }
      });
      (currentRuntime.work_items || []).filter(isOpenWork).forEach(function (item) {
        var workKey = "work_item:" + item.id;
        if (!known[workKey]) {
          rows.push({ key: workKey, severity: item.status === "blocked" ? "high" : "medium", title: item.title,
            allocationId: item.allocation_id, ownerId: item.owner_id, dueAt: item.due_at, status: item.status,
            action: "complete or replan" });
        }
      });
    }
    return connectedAllocationId ? rows.filter(function (row) { return row.allocationId === connectedAllocationId; }) : rows;
  }

  function renderRiskLedger() {
    var rows = inboxRows();
    var selectedAllocation = connectedAllocationId ? allocationFor(connectedAllocationId) : null;
    var filterClear = element("inbox-filter-clear");
    filterClear.hidden = !selectedAllocation;
    filterClear.textContent = t("showAllDecisions");
    if (!rows.length) {
      element("inbox-summary").textContent = selectedAllocation ?
        message("decisionsForField", { field: fieldLabel(selectedAllocation.operational_block_name) }) + " · " + t("noDecision") :
        (currentInboxMode === "all" ? t("nothingWaiting") : t("noDecision"));
      setHtml("portfolio-ledger", '<tr><td colspan="6" class="table-empty">' + escapeHtml(t("nothingWaiting")) + '</td></tr>');
      renderHomeMetrics();
      return;
    }
    var summary = currentInboxMode === "all" ?
      message("allDecisions", { count: formatCount(rows.length) }) :
      message(rows.length === 1 ? "priorityDecision" : "priorityDecisions", { count: formatCount(rows.length) });
    element("inbox-summary").textContent = selectedAllocation ?
      message("decisionsForField", { field: fieldLabel(selectedAllocation.operational_block_name) }) + " · " + summary : summary;
    setHtml("portfolio-ledger", rows.map(function (item) {
      return '<tr><td><span class="severity severity-' + escapeHtml(item.severity) + '">' + escapeHtml(readable(item.severity)) +
        '</span></td><th scope="row">' + escapeHtml(sampleText(item.title)) + '</th><td>' + escapeHtml(fieldNameFor(item.allocationId)) +
        '</td><td>' + escapeHtml(personName(item.ownerId)) + '</td><td>' + escapeHtml(formatTime(item.dueAt)) +
        '</td><td><span class="status">' + escapeHtml(readable(item.status)) + '</span></td></tr>';
    }).join(""));
    renderHomeMetrics();
  }

  function portfolioActionDetail(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type !== "field_information_request") {
      return readable(item.action);
    }
    var owner = item.owner_id ? personName(item.owner_id) : t("noFieldPerson");
    var due = item.due_at ? " · " + t("due") + " " + formatTime(item.due_at) : "";
    var proof = item.proof_required ? " · " + t("fieldProofRequired") : " · " + t("fieldUpdateRequested");
    if (item.status === "draft") {
      return t("fieldAsk") + " · " + owner + " " + t("fieldAskNeedsReview") + proof + ".";
    }
    if (item.status === "ready") {
      return t("fieldAsk") + " · " + owner + " " + t("fieldAskReady") + due + proof + ".";
    }
    return t("awaitingFieldAnswer") + " " + owner + due + proof + ".";
  }

  function laneStatusLabel(status) {
    var labels = {
      ready: "ready",
      context_available: "context ready",
      review_needed: "review needed",
      attention: "needs attention",
      needs_first_farm: "start here",
      needs_active_crop: "needs crop plan",
      needs_first_observation: "needs field check",
      needs_verified_district: "needs district",
      needs_lab_report: "needs lab report",
      needs_field_boundary: "needs boundary",
      needs_market_mapping: "needs market mapping",
      not_connected: "not connected",
      access_review: "access review",
      not_run: "not run"
    };
    return labels[status] || readable(status);
  }

  function laneClass(status) {
    return ["ready", "context_available"].indexOf(status) !== -1 ? "is-ready" :
      status === "review_needed" || status === "attention" ? "is-attention" : "is-gated";
  }

  function fallbackDataLanes() {
    return [
      { name: "Field truth", status: "needs_first_farm", source: "Field team + retained FFL evidence", fact: "Set up the first farm to begin the field loop.", limitation: "Public context never replaces field evidence.", next_move: "Prepare the first farm." },
      { name: "Weather", status: "needs_first_farm", source: "India Meteorological Department (IMD)", fact: "District context is not connected yet.", limitation: "Weather is context, not a field reading or instruction.", next_move: "Verify the farm district." },
      { name: "Soil & water", status: "needs_first_farm", source: "Reviewed lab report + field measurement", fact: "No soil baseline is ready yet.", limitation: "Predicted soil data does not replace a lab report.", next_move: "Retain one reviewed lab report." },
      { name: "Satellite", status: "needs_first_farm", source: "Copernicus Sentinel-2", fact: "No farm or field boundary is ready yet.", limitation: "Imagery is corroboration, never diagnosis.", next_move: "Build field truth before imagery." },
      { name: "Market", status: "needs_first_farm", source: "AGMARKNET / data.gov.in", fact: "No crop or market mapping is ready yet.", limitation: "Mandi context is not a sale price.", next_move: "Record the active crop first." }
    ];
  }

  function renderDataLanes(snapshot) {
    var lanes = snapshot && Array.isArray(snapshot.lanes) && snapshot.lanes.length === 5 ? snapshot.lanes : fallbackDataLanes();
    setHtml("data-lanes", lanes.map(function (lane) {
      var status = lane.status || "not_connected";
      return '<article class="data-lane ' + laneClass(status) + '">' +
        '<div class="data-lane-heading"><h4>' + escapeHtml(lane.name) + '</h4><span class="status">' +
        escapeHtml(laneStatusLabel(status)) + '</span></div>' +
        '<p class="data-lane-fact">' + escapeHtml(lane.fact) + '</p>' +
        '<p class="data-lane-source">' + escapeHtml(lane.source) + '</p>' +
        '<p class="data-lane-limit">' + escapeHtml(lane.limitation) + '</p>' +
        '<p class="data-lane-next"><strong>Next</strong> ' + escapeHtml(lane.next_move) + '</p>' +
        '</article>';
    }).join(""));
  }

  function renderDataLanesUnavailable() {
    renderDataLanes({ lanes: fallbackDataLanes() });
  }

  function setProfileLink(id, url, label) {
    var link = element(id);
    if (!url) {
      link.hidden = true;
      link.removeAttribute("href");
      return;
    }
    link.href = url;
    link.textContent = label;
    link.hidden = false;
  }

  function renderMapExplorer(profile) {
    var configured = profile && profile.configured === true;
    element("map-stage-guard").textContent = "Public coverage only";
    if (!configured) {
      element("map-stage-note").textContent = "No approved public operating area is configured yet.";
      setHtml("map-explorer", '<p class="map-empty">This map stays empty until a reviewed public hub or operating area is configured.</p>');
      setHtml("map-facts", '<div><dt>Farm locations</dt><dd>Not supplied</dd></div><div><dt>Supply villages</dt><dd>Not supplied</dd></div>');
      setProfileLink("map-source", null, "");
      return;
    }
    var facts = [];
    if (profile.public_hub_label) {
      facts.push('<div><dt>Public anchor</dt><dd>' + escapeHtml(profile.public_hub_label) + "</dd></div>");
    }
    if (profile.network_summary) {
      facts.push('<div><dt>Public network</dt><dd>' + escapeHtml(profile.network_summary) + "</dd></div>");
    }
    facts.push('<div><dt>Supply villages</dt><dd>Waiting for Fortune’s reviewed village hierarchy.</dd></div>');
    facts.push('<div><dt>Verified fields</dt><dd>Waiting for a reviewed farm manifest with location proof.</dd></div>');
    setHtml("map-facts", facts.join(""));
    setProfileLink("map-source", profile.source_url, "View public source");
    if (!profile.map_embed_url) {
      element("map-stage-note").textContent = "Public context is configured, but no map anchor has been approved.";
      setHtml("map-explorer", '<p class="map-empty">No map anchor is configured. Partner farms and field boundaries are never guessed here.</p>');
      return;
    }
    element("map-stage-note").textContent = "The mark is a public hub or coverage anchor. It is not a partner farm or a field boundary.";
    setHtml("map-explorer", '<iframe title="Approved public operating footprint" loading="lazy" referrerpolicy="no-referrer" src="' +
      escapeHtml(profile.map_embed_url) + '"></iframe>');
  }

  function renderOperatingProfile(profile) {
    var configured = profile && profile.configured === true;
    var displayName = configured ? text(profile.display_name) : "No operating profile set";
    element("wordmark-name").textContent = configured ? displayName : "AGRO CEO";
    element("profile-heading").textContent = displayName;
    if (!configured) {
      element("profile-summary").textContent = "Add approved public operating context in deployment settings. No farm locations are guessed.";
      setHtml("profile-facts", "");
      setProfileLink("profile-website", null, "");
      setProfileLink("profile-source", null, "");
      renderMapExplorer(profile);
      return;
    }
    element("profile-summary").textContent = "Public operating context only. It is not a field map or a source of record.";
    var facts = [];
    if (profile.coverage_label) {
      facts.push('<div><dt>Operating area</dt><dd>' + escapeHtml(profile.coverage_label) + "</dd></div>");
    }
    if (profile.network_summary) {
      facts.push('<div><dt>Publicly stated network</dt><dd>' + escapeHtml(profile.network_summary) + "</dd></div>");
    }
    if (profile.public_hub_label) {
      facts.push('<div><dt>Public hub</dt><dd>' + escapeHtml(profile.public_hub_label) + "</dd></div>");
    }
    setHtml("profile-facts", facts.join("") || '<p class="empty-state">No public coverage details configured.</p>');
    setProfileLink("profile-website", profile.website_url, "Open company site");
    setProfileLink("profile-source", profile.source_url, "View public source");
    if (!profile.map_embed_url) {
      renderMapExplorer(profile);
      return;
    }
    renderMapExplorer(profile);
  }

  function renderOperatingProfileUnavailable() {
    renderOperatingProfile({ configured: false });
  }

  function countStatusItems(statuses) {
    if (!statuses || typeof statuses !== "object") {
      return 0;
    }
    return Object.keys(statuses).reduce(function (total, status) {
      return total + (typeof statuses[status] === "number" ? statuses[status] : 0);
    }, 0);
  }

  function renderLearning(portfolio) {
    var learning = portfolio.learning || {};
    var trialStatuses = learning.trials && learning.trials.by_status;
    var playbookStatuses = learning.playbooks && learning.playbooks.by_status;
    var availability = learning.availability ? readable(learning.availability) : "unavailable";
    if (availability !== "available") {
      setHtml("portfolio-learning", '<p class="empty-state portfolio-unavailable">Learning context is ' +
        escapeHtml(availability) + '.</p>');
      return;
    }
    setHtml("portfolio-learning", '<dl class="portfolio-counts"><div><dt>Trials</dt><dd>' +
      countStatusItems(trialStatuses) + '</dd></div><div><dt>Playbooks</dt><dd>' +
      countStatusItems(playbookStatuses) + '</dd></div></dl>');
  }

  function renderPortfolio(portfolio) {
    if (!portfolio || typeof portfolio !== "object") {
      renderPortfolioUnavailable();
      return;
    }
    if (sampleMode && !listedItems(portfolio.risk_action_ledger).length) {
      currentPortfolio = samplePortfolio();
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    currentPortfolio = portfolio;
    if (currentRuntime) {
      renderDailyDirection();
    }
    renderRiskLedger();
    element("portfolio-status").textContent = "Actions updated just now.";
    renderHomeMetrics();
  }

  function renderPilotReadiness(readiness) {
    var progress = readiness && readiness.progress ? readiness.progress : { completed: 0, total: 6 };
    var stages = readiness && Array.isArray(readiness.stages) ? readiness.stages : [];
    var nextStage = readiness && readiness.next_stage ? readiness.next_stage : null;
    element("today-heading").textContent = interfaceLocale === "hi" ? "पहला खेत" : "First farm";
    element("today-count").textContent = progress.completed + "/" + progress.total;
    element("today-summary").textContent = nextStage ?
      "Start with " + nextStage.title.toLowerCase() + "." :
      "The minimum field loop is ready.";
    setHtml("today-list", stages.slice(0, 3).map(function (stage) {
      var ready = stage.status === "ready";
      return '<button class="queue-item foundation-item foundation-action" type="button" data-first-farm="true"><span class="item-title"><h3>' +
        escapeHtml(stage.title) + '</h3><span class="status">' +
        (ready ? "ready" : "next") + '</span></span><span>' +
        escapeHtml(ready ? "Recorded and ready for the field loop." : stage.next_action) +
        '</span></button>';
    }).join("") || '<p class="empty-state">The first farm has not been prepared yet.</p>');
    element("active-work-count").textContent = progress.completed;
    element("submitted-work-count").textContent = progress.total;
    setHtml("active-work-summary", "<span>Foundations ready</span>");
    setHtml("submitted-work-summary", "<span>Minimum needed</span>");
  }

  function loadPilotReadiness() {
    fetch(pilotReadinessUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load first-farm readiness.");
        }
        return response.json();
      })
      .then(renderPilotReadiness)
      .catch(function () {
        element("today-heading").textContent = interfaceLocale === "hi" ? "पहला खेत" : "First farm";
        element("today-count").textContent = "0/6";
        element("today-summary").textContent = "Prepare one real farm before external data can help.";
        setHtml("today-list", '<p class="empty-state">Farm, field, people, place, soil report, then the first work loop.</p>');
      });
  }

  function allocationLabel(allocation) {
    if (!allocation) {
      return "No active crop allocation";
    }
    return (allocation.operational_block_name || "Field") + " · " + allocation.crop_name +
      (allocation.cultivar ? " · " + allocation.cultivar : "");
  }

  function activeAllocation(runtime) {
    var source = runtime || currentRuntime || {};
    var allocations = Array.isArray(source.allocations) ? source.allocations : [];
    var focused = allocations.filter(function (allocation) { return allocation.id === focusedAllocationId; })[0] || null;
    if (!focused && allocations.length) {
      focused = allocations[0];
      focusedAllocationId = focused.id;
    }
    if (!allocations.length) {
      focusedAllocationId = null;
    }
    return focused;
  }

  function allocationCalendarFor(allocationId) {
    var record = allocationCalendars[allocationId];
    return record && record.state === "ready" ? record.data : null;
  }

  function scheduleValue(value) {
    var parsed = new Date(value || "");
    return isNaN(parsed.getTime()) ? Number.POSITIVE_INFINITY : parsed.getTime();
  }

  function nextOpenWork(allocationId, runtime) {
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    return workItems.filter(function (item) {
      return item.allocation_id === allocationId && isOpenWork(item);
    }).sort(function (left, right) {
      return scheduleValue(left.due_at) - scheduleValue(right.due_at);
    })[0] || null;
  }

  function latestUpdateForAllocation(allocation, runtime) {
    var update = latestFieldUpdate(runtime);
    if (!update || !allocation) {
      return null;
    }
    var matchingAllocations = (runtime.allocations || []).filter(function (candidate) {
      return candidate.operational_block_name === update.operational_block_name && candidate.crop_name === update.crop_name;
    });
    return matchingAllocations.length === 1 && matchingAllocations[0].id === allocation.id ? update : null;
  }

  function reviewableEvidenceForAllocation(allocationId) {
    var signals = currentPortfolio && currentPortfolio.field_signals && currentPortfolio.field_signals.open;
    var items = signals && Array.isArray(signals.items) ? signals.items : [];
    return items.filter(function (item) {
      return item.allocation_id === allocationId;
    }).sort(function (left, right) {
      return scheduleValue(right.received_at || right.observed_at) - scheduleValue(left.received_at || left.observed_at);
    })[0] || null;
  }

  function allocationSnapshot(allocation, runtime) {
    var calendarRecord = allocationCalendars[allocation.id];
    var calendar = allocationCalendarFor(allocation.id);
    var work = nextOpenWork(allocation.id, runtime);
    var update = latestUpdateForAllocation(allocation, runtime);
    var reviewableEvidence = reviewableEvidenceForAllocation(allocation.id);
    var missing = [];
    var stage;
    var stageMissing = false;
    var stageGap = null;

    if (calendarRecord && calendarRecord.state === "loading") {
      stage = "Loading stage plan…";
    } else if (!calendar) {
      stage = "Stage plan unavailable";
      stageMissing = true;
      stageGap = "stage plan";
    } else if (calendar.current_stage) {
      stage = "Confirmed: " + calendar.current_stage.stage_name;
    } else if (calendar.next_checkpoint) {
      stage = "Next check: " + calendar.next_checkpoint.stage_name + " · " + formatTime(calendar.next_checkpoint.planned_for);
      stageMissing = true;
      stageGap = "stage confirmation";
    } else {
      stage = "No stage check planned";
      stageMissing = true;
      stageGap = "stage check";
    }
    if (stageGap) {
      missing.push(stageGap);
    }

    if (!work) {
      missing.push("next work");
    }
    if (!update) {
      missing.push("field record");
    }
    if (reviewableEvidence && reviewableEvidence.evidence_attached === false) {
      missing.push("retained evidence");
    }
    return {
      stage: stage,
      stageMissing: stageMissing,
      nextWork: work ? work.title + " · " + formatTime(work.due_at) : "No open work planned",
      workMissing: !work,
      owner: work ? personName(work.owner_id) : "No work owner set",
      ownerMissing: !work || personName(work.owner_id) === "Unassigned",
      fieldRecord: reviewableEvidence ?
        (reviewableEvidence.evidence_attached ? "Evidence attached · observed " + formatTime(reviewableEvidence.observed_at) :
          "Field signal has no attached evidence") :
        (update ? "Field record observed " + formatTime(update.observed_at) + " · evidence detail unavailable" :
          "No field update recorded"),
      fieldRecordMissing: !update || Boolean(reviewableEvidence && reviewableEvidence.evidence_attached === false),
      missing: missing
    };
  }

  function boardStatusLabel(status) {
    var labels = {
      ready: "recorded",
      attention: "attention",
      missing: "needs record",
      private: "private",
      unavailable: "unavailable"
    };
    return labels[status] || "review";
  }

  function boardPiece(view, icon, label, status, count, detail, action) {
    return '<button class="board-piece is-' + escapeHtml(status) + '" type="button" data-board-view="' +
      escapeHtml(view) + '"><span class="board-piece-top"><span class="board-piece-icon material-symbols-outlined" aria-hidden="true">' +
      escapeHtml(icon) + '</span><span class="status">' + escapeHtml(boardStatusLabel(status)) +
      '</span></span><span class="board-piece-label">' + escapeHtml(label) + '</span><strong>' +
      escapeHtml(count) + '</strong><span class="board-piece-detail">' + escapeHtml(detail) +
      '</span><span class="board-piece-action">' + escapeHtml(action) +
      ' <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span></span></button>';
  }

  function renderOperationsBoard(runtime) {
    var source = runtime || currentRuntime;
    if (!source) {
      setHtml("operations-board", '<p class="empty-state">Set up one reviewed field to begin the operations board.</p>');
      return;
    }
    var allocations = Array.isArray(source.allocations) ? source.allocations : [];
    var workItems = Array.isArray(source.work_items) ? source.work_items : [];
    var exceptions = Array.isArray(source.exceptions) ? source.exceptions.filter(isOpenException) : [];
    var people = Array.isArray(source.people) ? source.people : [];
    var relationships = source.person_operating_relationships && Array.isArray(source.person_operating_relationships.items) ?
      source.person_operating_relationships.items : [];
    var snapshots = allocations.map(function (allocation) { return allocationSnapshot(allocation, source); });
    var fieldNames = allocations.map(function (allocation) { return allocation.operational_block_name || "Field"; })
      .filter(function (name, index, values) { return values.indexOf(name) === index; });
    var fieldEvidenceGaps = snapshots.filter(function (snapshot) { return snapshot.fieldRecordMissing; }).length;
    var cropPlanGaps = snapshots.filter(function (snapshot) { return snapshot.stageMissing || snapshot.workMissing; }).length;
    var unownedWork = workItems.filter(function (item) { return isOpenWork(item) && !item.owner_id; }).length;
    var fieldTeam = people.filter(isFieldWorker);
    var fieldStatus = !fieldNames.length ? "missing" : (exceptions.length ? "attention" :
      (fieldEvidenceGaps ? "missing" : "ready"));
    var fieldDetail = !fieldNames.length ? "No reviewed operating block yet." : exceptions.length ?
      exceptions.length + (exceptions.length === 1 ? " open field issue." : " open field issues.") : fieldEvidenceGaps ?
      fieldEvidenceGaps + (fieldEvidenceGaps === 1 ? " field needs a record." : " fields need records.") :
      "Reviewed field record is present.";
    var cropStatus = !allocations.length ? "missing" : (cropPlanGaps ? "attention" : "ready");
    var cropDetail = !allocations.length ? "No active crop allocation yet." : cropPlanGaps ?
      cropPlanGaps + (cropPlanGaps === 1 ? " crop needs a stage or work plan." : " crops need a stage or work plan.") :
      "Stage and next work are in place.";
    var teamStatus = !fieldTeam.length ? "missing" : (unownedWork || !relationships.length ? "attention" : "ready");
    var teamDetail = !fieldTeam.length ? "No canonical field team yet." : unownedWork ?
      unownedWork + (unownedWork === 1 ? " open item has no owner." : " open items have no owner.") : !relationships.length ?
      "Reviewed team scope is still needed." : "Roles and scopes are recorded.";
    var inboxItems = exceptions.length + workItems.filter(isOpenWork).length;
    var inboxStatus = !inboxItems ? "ready" : (exceptions.length || unownedWork || workItems.some(isOverdue) ? "attention" : "ready");
    var inboxDetail = !inboxItems ? "No open issues or work items." :
      inboxItems + (inboxItems === 1 ? " item needs a decision or next step." : " items need a decision or next step.");
    var farmerStatus = "private";
    var farmerCount = "Private programme";
    var farmerDetail = "Unlock manager actions to read source coverage.";
    if (managerSessionAuthenticated && currentProgramme && currentProgramme.metrics) {
      var coverage = currentProgramme.metrics.coverage || {};
      var takenKit = Number(coverage.taken_kit) || 0;
      var recent = Number(coverage.recent) || 0;
      var neverVisited = Number(coverage.never_visited) || 0;
      var recentShare = takenKit ? recent / takenKit : 0;
      farmerStatus = !takenKit ? "unavailable" : (recentShare >= 0.75 ? "ready" : "attention");
      farmerCount = takenKit ? formatCount(takenKit) + " programme members" : "No published members";
      farmerDetail = takenKit ? formatCount(recent) + " reached in 14 days · " + formatCount(neverVisited) + " never visited." :
        "No published TrackWick programme context.";
    }
    setHtml("operations-board",
      boardPiece("farms", "landscape", "Farms", fieldStatus, fieldNames.length + (fieldNames.length === 1 ? " operating block" : " operating blocks"), fieldDetail + " " + cropDetail, "Open farms") +
      boardPiece("farmers", "diversity_3", "Farmers", farmerStatus, farmerCount, farmerDetail + " Source coverage is not a named farmer record.", "Open farmers") +
      boardPiece("workers", "groups", "Field workers", teamStatus, fieldTeam.length + (fieldTeam.length === 1 ? " field worker" : " field workers"), teamDetail, "Open field workers") +
      boardPiece("inbox", "inbox", "Inbox", inboxStatus, inboxItems + (inboxItems === 1 ? " open item" : " open items"), inboxDetail, "Open inbox")
    );
  }

  function allocationFact(label, value, missing) {
    return '<div><dt>' + escapeHtml(label) + '</dt><dd' + (missing ? ' class="is-missing"' : '') + '>' +
      escapeHtml(value) + '</dd></div>';
  }

  function renderAllocationCards(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    if (!allocations.length) {
      element("allocation-summary").textContent = "No active crop allocation has been recorded yet.";
      setHtml("allocation-list", '<p class="empty-state">Add a verified field and a crop allocation to start the operating loop.</p>');
      setHtml("farm-table-body", '<tr><td colspan="4" class="table-empty">No verified fields yet.</td></tr>');
      return;
    }
    element("allocation-summary").textContent = allocations.length === 1 ?
      "1 " + t("reviewedField") + " · " + t("sampleLocationShort") :
      formatCount(allocations.length) + " " + t("reviewedFields");
    setHtml("allocation-list", allocations.map(function (allocation) {
      var assignedWork = (runtime.work_items || []).filter(function (item) {
        return item.allocation_id === allocation.id && isOpenWork(item);
      }).length;
      var headlineValue = Number(allocation.area_hectares) ? areaLabel(allocation.area_hectares) : formatCount(assignedWork);
      var headlineLabel = Number(allocation.area_hectares) ? t("area") : (assignedWork === 1 ? t("openAction") : t("openActions"));
      var fieldName = fieldLabel(allocation.operational_block_name);
      var farmName = allocation.farm_name ? sampleText(allocation.farm_name) + " · " : "";
      var characteristics = [
        allocation.location_label ? t("location") + " · " + sampleText(allocation.location_label) : "",
        allocation.crop_name ? t("crop") + " · " + cropLabel(allocation.crop_name) : "",
        allocation.cultivar ? t("variety") + " · " + allocation.cultivar : "",
        assignedWork ? t("risk") + " · " + formatCount(assignedWork) + " " + (assignedWork === 1 ? t("openAction") : t("openActions")) : ""
      ].filter(Boolean);
      return '<button class="directory-card allocation-card' + (connectedAllocationId === allocation.id ? " is-connected" : "") + '" type="button" data-record-kind="farm" data-record-id="' + escapeHtml(allocation.id) + '">' +
        '<div class="allocation-card-heading"><h3>' + escapeHtml(farmName + fieldName) + '</h3>' +
        '<span class="status">' + escapeHtml(t("verified")) + '</span></div>' +
        '<p class="allocation-crop">' + escapeHtml(cropLabel(allocation.crop_name)) + '</p>' +
        '<div class="directory-card-metric"><strong>' + escapeHtml(headlineValue) + '</strong><span>' + escapeHtml(headlineLabel) + '</span></div>' +
        '<ul class="directory-characteristics">' + characteristics.map(function (trait) { return '<li>' + escapeHtml(trait) + '</li>'; }).join("") + '</ul>' +
        '</button>';
    }).join(""));
    setHtml("farm-table-body", allocations.map(function (allocation) {
      return '<tr><th scope="row">' + escapeHtml(fieldLabel(allocation.operational_block_name)) + '</th><td>' +
        escapeHtml(cropLabel(allocation.crop_name)) + '</td><td>' + escapeHtml(allocation.cultivar || "—") +
        '</td><td><span class="status">' + escapeHtml(t("verified")) + '</span></td></tr>';
    }).join(""));
  }

  function renderCards(runtime) {
    renderAllocationCards(runtime);
  }

  function clearLeafletMap(containerId, emptyMessage) {
    var container = element(containerId);
    if (leafletMaps[containerId]) {
      leafletMaps[containerId].remove();
      delete leafletMaps[containerId];
    }
    container.innerHTML = '<p class="map-empty-state">' + escapeHtml(emptyMessage) + '</p>';
  }

  function mapPopup(feature) {
    var properties = feature && feature.properties ? feature.properties : {};
    var parts = [sampleText(properties.plot_label || t("reviewedField"))];
    if (properties.crop_name) {
      parts.push(cropLabel(properties.crop_name) + (properties.cultivar ? " · " + properties.cultivar : ""));
    }
    if (properties.area_hectares) {
      parts.push(areaLabel(properties.area_hectares));
    }
    if (properties.location_label) {
      parts.push(sampleText(properties.location_label));
    }
    return escapeHtml(parts.join(" · "));
  }

  function renderMapCanvas(containerId, featureCollection) {
    var features = featureCollection && Array.isArray(featureCollection.features) ? featureCollection.features : [];
    if (!features.length) {
      clearLeafletMap(containerId, "No reviewed field geometry is available yet. A programme village or coverage count is never placed on this map.");
      return;
    }
    var container = element(containerId);
    if (!window.L) {
      clearLeafletMap(containerId, "The map library is unavailable. Reviewed field geometry remains protected until the map can load.");
      return;
    }
    if (leafletMaps[containerId]) {
      leafletMaps[containerId].remove();
    }
    container.innerHTML = "";
    var map = window.L.map(container, { zoomControl: true, attributionControl: true });
    leafletMaps[containerId] = map;
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);
    var layer = window.L.geoJSON(featureCollection, {
      style: { color: "#bc7a1e", weight: 2, fillColor: "#d8b14d", fillOpacity: 0.28 },
      pointToLayer: function (_feature, latlng) {
        return window.L.circleMarker(latlng, {
          radius: 7, color: "#173f2c", weight: 2, fillColor: "#d7aa3f", fillOpacity: 0.95
        });
      },
      onEachFeature: function (feature, featureLayer) {
        featureLayer.bindTooltip(mapPopup(feature), { sticky: true });
        var properties = feature && feature.properties ? feature.properties : {};
        if (properties.record_kind === "farm" && properties.record_id) {
          featureLayer.on("click", function () {
            connectFarm(properties.record_id);
            openRecordDialog("farm", properties.record_id);
          });
        }
      }
    }).addTo(map);
    var bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.3), { maxZoom: 13 });
    }
  }

  function renderFortuneMap(featureCollection) {
    currentFortuneMap = featureCollection || { type: "FeatureCollection", features: [] };
    var features = currentFortuneMap.features || [];
    var count = features.length;
    element("home-map-status").textContent = sampleMode ? t("sampleLocation") :
      (count ? formatCount(count) + " " + (count === 1 ? t("reviewedField") : t("reviewedFields")) : t("noReviewedGeometry"));
    element("home-map-note").textContent = sampleMode ? t("sampleGeometry") : (count ?
      "Map detail comes only from the latest published, reviewed farm manifest." :
      "Only manager-reviewed points and boundaries appear here. Programme coverage never becomes a farm pin.");
    element("farm-map-note").textContent = sampleMode ? t("sampleGeometry") : (count ?
      "The map uses the same reviewed farm geometry as Home." :
      "Only reviewed field geometry is shown. No source village is treated as a farm point.");
    renderMapCanvas("home-map-canvas", currentFortuneMap);
    renderMapCanvas("farm-map-canvas", currentFortuneMap);
  }

  function renderFortuneMapUnavailable() {
    if (sampleMode) {
      renderFortuneMap(sampleMap());
      return;
    }
    currentFortuneMap = { type: "FeatureCollection", features: [] };
    element("home-map-status").textContent = managerSessionAuthenticated ? "Map unavailable" : "Unlock to reveal map";
    element("home-map-note").textContent = managerSessionAuthenticated ?
      "Reviewed field geometry could not be loaded right now." :
      "Manager access is required before private reviewed field geometry can be shown.";
    element("farm-map-note").textContent = element("home-map-note").textContent;
    clearLeafletMap("home-map-canvas", element("home-map-note").textContent);
    clearLeafletMap("farm-map-canvas", element("farm-map-note").textContent);
  }

  function loadFortuneMap() {
    if (!managerSessionAuthenticated) {
      renderFortuneMapUnavailable();
      return Promise.resolve();
    }
    return fetch(fortuneMapUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Reviewed field geometry is unavailable.");
        }
        return response.json();
      })
      .then(renderFortuneMap)
      .catch(renderFortuneMapUnavailable);
  }

  function personFor(personId) {
    var people = currentRuntime && Array.isArray(currentRuntime.people) ? currentRuntime.people : [];
    return people.filter(function (person) { return person.id === personId; })[0] || null;
  }

  function personName(personId) {
    var person = personFor(personId);
    return person ? person.name : "Unassigned";
  }

  function workFor(workId) {
    var workItems = currentRuntime && Array.isArray(currentRuntime.work_items) ? currentRuntime.work_items : [];
    return workItems.filter(function (item) { return item.id === workId; })[0] || null;
  }

  function allocationFor(allocationId) {
    var allocations = currentRuntime && Array.isArray(currentRuntime.allocations) ? currentRuntime.allocations : [];
    return allocations.filter(function (allocation) { return allocation.id === allocationId; })[0] || null;
  }

  function fieldNameFor(allocationId) {
    var allocation = allocationFor(allocationId);
    return allocation && allocation.operational_block_name ? fieldLabel(allocation.operational_block_name) : t("field");
  }

  function exceptionFor(exceptionId) {
    var exceptions = currentRuntime && Array.isArray(currentRuntime.exceptions) ? currentRuntime.exceptions : [];
    return exceptions.filter(function (item) { return item.id === exceptionId; })[0] || null;
  }

  function setFocusAction(label, targetView, exceptionId) {
    focusTargetView = targetView;
    focusExceptionId = exceptionId || null;
    element("focus-action-label").textContent = label;
  }

  function isFarmer(person) {
    return person && ["grower", "landholder", "lessee"].indexOf(person.role) !== -1;
  }

  function isFieldWorker(person) {
    return person && ["field_operator", "agronomist"].indexOf(person.role) !== -1;
  }

  function personDirectoryData(person, runtime, relationships, relationshipAvailability) {
    var workItems = Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var assignedItems = workItems.filter(function (item) {
      return item.owner_id === person.id && isOpenWork(item);
    });
    var fields = assignedItems.map(function (item) { return fieldNameFor(item.allocation_id); })
      .filter(function (value, index, values) { return values.indexOf(value) === index; });
    var assignments = relationships.filter(function (relationship) {
      return relationship.person_id === person.id;
    });
    var assignmentCopy = assignments.length ? assignments.map(function (relationship) {
      return readable(relationship.role) + (relationship.scope_name ? " · " + fieldLabel(relationship.scope_name) : "");
    }).join(" · ") : (relationshipAvailability === "available" ? "No field relationship recorded." :
      (relationshipAvailability === "not_configured" ? "Field relationship setup is pending." : "Field relationship summary unavailable."));
    return {
      id: person.id,
      name: person.name,
      role: readable(person.role),
      scope: assignmentCopy,
      openWork: assignedItems.length,
      fields: fields,
      fieldCount: assignments.length || fields.length,
      isFarmer: isFarmer(person),
      characteristics: Array.isArray(person.characteristics) ? person.characteristics.map(sampleText) : []
    };
  }

  function personCardMarkup(personData) {
    var metricValue = personData.isFarmer ? formatCount(personData.fieldCount) : formatCount(personData.openWork);
    var metricLabel = personData.isFarmer ? (personData.fieldCount === 1 ? t("fieldCount") : t("fieldCountPlural")) :
      (personData.openWork === 1 ? t("openAction") : t("openActions"));
    var characteristics = personData.characteristics.length ? personData.characteristics : [personData.scope];
    return '<button class="directory-card person-card" type="button" data-record-kind="' + (personData.isFarmer ? "farmer" : "worker") +
      '" data-record-id="' + escapeHtml(personData.id) + '"><h3>' + escapeHtml(personData.name) + '</h3>' +
      '<p class="person-role">' + escapeHtml(personData.role) + '</p>' +
      '<div class="directory-card-metric"><strong>' + escapeHtml(metricValue) + '</strong><span>' + escapeHtml(metricLabel) + '</span></div>' +
      '<ul class="directory-characteristics">' + characteristics.map(function (trait) { return '<li>' + escapeHtml(trait) + '</li>'; }).join("") + '</ul>' +
      '<p class="person-assignment">' + escapeHtml(personData.scope) + '</p></button>';
  }

  function peopleTableMarkup(people) {
    if (!people.length) {
      return '<tr><td colspan="4" class="table-empty">No reviewed people records are available yet.</td></tr>';
    }
    return people.map(function (person) {
      return '<tr><th scope="row">' + escapeHtml(person.name) + '</th><td>' + escapeHtml(person.role) +
        '</td><td>' + escapeHtml(person.scope) + '</td><td>' + escapeHtml(formatCount(person.openWork) + " " + (person.openWork === 1 ? t("openAction") : t("openActions"))) +
        '</td></tr>';
    }).join("");
  }

  function renderPeople(runtime) {
    var people = Array.isArray(runtime.people) ? runtime.people : [];
    var relationshipSummary = runtime.person_operating_relationships || {};
    var relationships = Array.isArray(relationshipSummary.items) ? relationshipSummary.items : [];
    var relationshipAvailability = relationshipSummary.availability || "not_configured";
    var farmers = people.filter(isFarmer).map(function (person) {
      return personDirectoryData(person, runtime, relationships, relationshipAvailability);
    });
    var workers = people.filter(isFieldWorker).map(function (person) {
      return personDirectoryData(person, runtime, relationships, relationshipAvailability);
    });
    setHtml("farmer-list", farmers.length ? farmers.map(personCardMarkup).join("") :
      '<p class="empty-state">No reviewed farmer record is available yet. Programme coverage stays separate.</p>');
    setHtml("worker-list", workers.length ? workers.map(personCardMarkup).join("") :
      '<p class="empty-state">No reviewed field worker record is available yet. Daily source activity stays aggregate until reviewed.</p>');
    setHtml("farmer-table-body", peopleTableMarkup(farmers));
    setHtml("worker-table-body", peopleTableMarkup(workers));
  }

  function recordTraits(items) {
    element("record-dialog-characteristics").innerHTML = items.filter(Boolean).map(function (item) {
      return "<li>" + escapeHtml(item) + "</li>";
    }).join("");
  }

  function openRecordDialog(kind, id, syncRoute) {
    var title = "";
    var metric = "—";
    var metricLabel = "";
    var traits = [];
    var context = "";
    if (kind === "farm") {
      var allocation = allocationFor(id);
      if (!allocation) {
        return;
      }
      connectFarm(id);
      var work = (currentRuntime.work_items || []).filter(function (item) {
        return item.allocation_id === allocation.id && isOpenWork(item);
      }).length;
      title = (allocation.farm_name ? sampleText(allocation.farm_name) + " · " : "") + fieldLabel(allocation.operational_block_name);
      metric = Number(allocation.area_hectares) ? areaLabel(allocation.area_hectares) : formatCount(work);
      metricLabel = Number(allocation.area_hectares) ? t("area") : (work === 1 ? t("openAction") : t("openActions"));
      traits = [
        allocation.location_label ? t("location") + " · " + sampleText(allocation.location_label) : "",
        allocation.crop_name ? t("crop") + " · " + cropLabel(allocation.crop_name) : "",
        allocation.cultivar ? t("variety") + " · " + allocation.cultivar : "",
        work ? t("risk") + " · " + formatCount(work) + " " + (work === 1 ? t("openAction") : t("openActions")) : ""
      ];
      context = t("reviewedRecord");
    } else {
      var person = personFor(id);
      if (!person) {
        return;
      }
      var runtime = currentRuntime || {};
      var relationships = runtime.person_operating_relationships && Array.isArray(runtime.person_operating_relationships.items) ?
        runtime.person_operating_relationships.items : [];
      var data = personDirectoryData(person, runtime, relationships, "available");
      title = data.name;
      metric = data.isFarmer ? formatCount(data.fieldCount) : formatCount(data.openWork);
      metricLabel = data.isFarmer ? (data.fieldCount === 1 ? t("fieldCount") : t("fieldCountPlural")) :
        (data.openWork === 1 ? t("openAction") : t("openActions"));
      traits = data.characteristics.length ? data.characteristics : [data.scope];
      context = data.scope;
    }
    element("record-dialog-kind").textContent = kind === "farm" ? t("field") : (kind === "farmer" ? t("farmer") : t("fieldWorker"));
    element("record-dialog-title").textContent = title;
    element("record-dialog-metric").textContent = metric;
    element("record-dialog-metric-label").textContent = metricLabel;
    element("record-dialog-context").textContent = context;
    recordTraits(traits);
    var action = element("record-dialog-action");
    action.hidden = kind !== "farm";
    action.textContent = kind === "farm" ? t("viewRelatedDecisions") : "";
    if (syncRoute !== false) {
      updateRecordRoute(kind, id);
    }
    var dialog = element("record-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function renderInboxWork(runtime) {
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var openItems = workItems.filter(isOpenWork);
    var selectedOwner = inboxOwnerId ? personFor(inboxOwnerId) : null;
    if (inboxOwnerId) {
      openItems = openItems.filter(function (item) { return item.owner_id === inboxOwnerId; });
    }
    element("inbox-clear-filter").hidden = !inboxOwnerId;
    element("inbox-clear-filter").textContent = selectedOwner ? "Show all work" : "Clear worker filter";
    if (!openItems.length) {
      setHtml("inbox-work-list", '<p class="empty-state">' + (selectedOwner ?
        escapeHtml(selectedOwner.name) + ' has no open reviewed work.' : "No open reviewed work is recorded.") + "</p>");
      return;
    }
    setHtml("inbox-work-list", openItems.slice(0, 8).map(function (item) {
      var owner = item.owner_id ? personName(item.owner_id) : "No owner";
      return '<article class="inbox-work-item"><div class="item-title"><h4>' + escapeHtml(item.title) + '</h4><span class="status">' +
        escapeHtml(readable(item.status)) + '</span></div><p class="work-field">' + escapeHtml(fieldNameFor(item.allocation_id)) +
        '</p><p class="today-item-detail">Owner · ' + escapeHtml(owner) + ' · due ' + escapeHtml(formatTime(item.due_at)) + '</p></article>';
    }).join(""));
  }

  function latestFieldUpdate(runtime) {
    return runtime && runtime.latest_field_update && typeof runtime.latest_field_update === "object" ?
      runtime.latest_field_update : null;
  }

  function setDailyDirection(status, title, note, officerActivity, visitGap, nextMove, confidence, targetView) {
    element("field-title").textContent = title;
    element("field-note").textContent = note;
    element("field-status").textContent = status;
    element("field-status").className = status === "attention" ? "severity severity-high" : "status";
    var labels = {
      farms: t("openFarms"),
      farmers: t("openFarmers"),
      workers: t("openWorkers"),
      inbox: t("openInbox"),
      settings: t("openSettings")
    };
    setFocusAction(labels[targetView] || "Open today", targetView, null);
  }

  function renderDailyDirection() {
    var programme = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!programme) {
      setDailyDirection(
        "reading", t("directionLoadingTitle"),
        t("directionLoadingNote"),
        t("dailyActivityLoading"), t("coverageLoadingShort"), t("openWorkers"), t("awaitingSignal"), "workers"
      );
      return;
    }
    var visits = programme.visits || {};
    var coverage = programme.coverage || {};
    var issues = programme.issues || {};
    var freshness = programme.freshness || {};
    var issueRows = Array.isArray(issues.by_issue) ? issues.by_issue : [];
    var officersWithoutVisit = Number(visits.active_officers_without_filed_visit) || 0;
    var activeOfficers = Number(visits.active_officers) || 0;
    var filedToday = Number(visits.filed_on_reporting_day) || 0;
    var filingOfficers = Number(visits.filing_officers) || 0;
    var overdue = Number(coverage.overdue) || 0;
    var neverVisited = Number(coverage.never_visited) || 0;
    var urgentIssue = issueRows.filter(function (issue) {
      return ["critical", "high"].indexOf(issue.highest_severity) !== -1;
    })[0] || null;
    var confidence = freshness.status === "available" ?
      "· " + formatAgeHours(freshness.age_hours) : "";

    if (officersWithoutVisit > 0) {
      setDailyDirection(
        "attention", t("coverageRiskTitle"),
        message("coverageRiskNote", { filed: formatCount(filedToday), filing: formatCount(filingOfficers), active: formatCount(activeOfficers) }),
        message("officersFiled", { filing: formatCount(filingOfficers), active: formatCount(activeOfficers) }), message("farmersOverdueMetric", { count: formatCount(overdue) }),
        t("reviewWorkerFollowUp"), confidence, "workers"
      );
      return;
    }
    if (urgentIssue) {
      setDailyDirection(
        "attention", message("cropInterventionTitle", { issue: readable(urgentIssue.issue_code) }),
        message("cropInterventionNote", { count: formatCount(urgentIssue.count), days: formatCount(issues.window_days || 7) }),
        message("visitsFiledMetric", { count: formatCount(filedToday) }), message("farmersOverdueMetric", { count: formatCount(overdue) }),
        t("reviewDecisionQueue"), confidence, "inbox"
      );
      return;
    }
    setDailyDirection(
      overdue ? "attention" : "reported", overdue ? t("coverageRepairTitle") : t("farmerCoverageCurrent"),
      overdue ? t("farmerOverdueNote") : t("noOverdueNote"),
      message("visitsFiledMetric", { count: formatCount(filedToday) }), message("neverVisitedMetric", { count: formatCount(neverVisited) }),
      t("reviewFarmerCoverage"), confidence, "farmers"
    );
  }

  function renderMorningBrief(brief) {
    var attention = brief && Array.isArray(brief.attention) ? brief.attention : [];
    renderToday(attention);
  }

  function todayDetail(item) {
    var entity = item && item.entity ? item.entity : {};
    var exception = entity.type === "exception_record" ? exceptionFor(entity.id) : null;
    var work = entity.type === "work_item" ? workFor(entity.id) : null;
    if (exception) {
      return "Owner · " + personName(exception.owner_id) + " · " + readable(exception.status);
    }
    if (work) {
      return fieldNameFor(work.allocation_id) + " · " + personName(work.owner_id) + " · due " + formatTime(work.due_at);
    }
    if (entity.type === "crop_stage_checkpoint") {
      return "Field check due.";
    }
    if (entity.type === "field_information_request") {
      var requestOwner = item.owner_id ? personName(item.owner_id) : t("noFieldPerson");
      var requestDue = item.due_at ? " · " + t("due") + " " + formatTime(item.due_at) : "";
      var proof = item.proof_required ? " · " + t("fieldProofRequired") : " · " + t("fieldUpdateRequested");
      return t("fieldAsk") + " · " + requestOwner + requestDue + proof;
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return "District context only. Check it against the field.";
    }
    return item && item.detail ? item.detail : "Needs a manager check.";
  }

  function todayNext(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type === "exception_record") {
      return "Review and assign the next step.";
    }
    if (entity.type === "work_item") {
      return "Complete it, replan it, or record why it is blocked.";
    }
    if (entity.type === "crop_stage_checkpoint") {
      return "Confirm the stage in the field.";
    }
    if (entity.type === "field_information_request") {
      return entity && item.action === "review_delivery_eligibility" ?
        t("checkDelivery") : t("reviewFieldAnswer");
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return "Check the source before changing field work.";
    }
    return "Check the farm record.";
  }

  function renderToday(items) {
    var currentItems = Array.isArray(items) ? items.slice(0, 3) : [];
    currentAttention = currentItems;
    element("today-count").textContent = currentItems.length;
    element("today-summary").textContent = currentItems.length ?
      (currentItems.length === 1 ? "One item needs a look." : currentItems.length + " items need a look.") :
      "Nothing needs a look right now.";
    if (!currentItems.length) {
      setHtml("today-list", '<p class="empty-state">No due work or open issue.</p>');
      return;
    }
    setHtml("today-list", currentItems.map(function (item, index) {
      var entity = item.entity || {};
      return '<button class="queue-item today-item today-action" type="button" data-today-index="' + index + '">' +
        '<div class="item-title"><h3>' + escapeHtml(item.title) + '</h3><span class="severity severity-' +
        safeSeverity(item.priority) + '">' + escapeHtml(item.priority) + '</span></div>' +
        '<p class="today-item-detail">' + escapeHtml(todayDetail(item)) + '</p>' +
        '<p class="today-item-next"><strong>Next</strong> ' + escapeHtml(todayNext(item)) + '</p>' +
        '<span class="detail-button">Open</span>' +
        '</button>';
    }).join(""));
  }

  function renderTodayFallback(runtime) {
    var exceptions = (runtime.exceptions || []).filter(isOpenException).map(function (item) {
      return { priority: item.severity === "critical" ? "critical" : "high", title: item.title,
        entity: { type: "exception_record", id: item.id } };
    });
    var work = (runtime.work_items || []).filter(function (item) {
      return item.status === "submitted" || (isOpenWork(item) && isOverdue(item));
    }).map(function (item) {
      return { priority: item.status === "submitted" ? "medium" : "high", title: item.title,
        entity: { type: "work_item", id: item.id } };
    });
    renderToday(exceptions.concat(work));
  }

  function loadMorningBrief(runtime) {
    if (!runtime || !runtime.operating_unit || !runtime.operating_unit.id) {
      return;
    }
    fetch("/api/v1/operating-units/" + encodeURIComponent(runtime.operating_unit.id) + "/morning-brief")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load the operating brief.");
        }
        return response.json();
      })
      .then(renderMorningBrief)
      .catch(function () {
        // The Home view remains fully useful from runtime data when the brief
        // cannot be composed. It is a read-only summary, never a source of record.
      });
  }

  function renderWork(runtime) {
    var allocation = activeAllocation(runtime);
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var openWork = allocation ? workItems.filter(function (item) {
      return item.allocation_id === allocation.id && isOpenWork(item);
    }) : [];
    element("work-context").textContent = allocation ? allocationLabel(allocation) : "No active crop allocation";
    if (!openWork.length) {
      setHtml("work-list", '<p class="empty-state">' + (allocation ?
        'No open work is linked to this crop allocation.' :
        'No farm work is shown until an active allocation exists.') + '</p>');
      return;
    }
    setHtml("work-list", openWork.map(function (item) {
      var overdue = isOverdue(item);
      return "<article class=\"queue-item\">" +
        "<p class=\"work-field\">" + escapeHtml(fieldNameFor(item.allocation_id)) + "</p>" +
        "<div class=\"item-title\"><h3>" + escapeHtml(item.title) + "</h3>" +
        "<span class=\"status status-" + escapeHtml(item.status) + "\">" + escapeHtml(item.status) + "</span></div>" +
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(personName(item.owner_id)) + "</dd></div>" +
        "<div><dt>Due</dt><dd>" + escapeHtml(formatTime(item.due_at)) + "</dd></div>" +
        "<div><dt>Timing</dt><dd class=\"" + (overdue ? "overdue" : "") + "\">" + (overdue ? "Overdue" : "On schedule") + "</dd></div></dl>" +
        "</article>";
    }).join(""));
  }

  function renderActionAllocationContext(runtime) {
    var allocation = activeAllocation(runtime);
    var context = element("actions-allocation-context");
    if (!allocation) {
      context.hidden = true;
      return;
    }
    context.hidden = false;
    element("actions-allocation-name").textContent = allocationLabel(allocation);
    element("actions-allocation-note").textContent =
      "Only risks and actions explicitly linked to this crop allocation are shown below. Operating-wide context stays in Home.";
  }

  function refreshFocusedAllocationExperience() {
    if (!currentRuntime) {
      return;
    }
    renderCards(currentRuntime);
    renderDailyDirection();
    renderOperationsBoard(currentRuntime);
    renderWork(currentRuntime);
    renderActionAllocationContext(currentRuntime);
    if (currentPortfolio) {
      renderRiskLedger(currentPortfolio);
    }
  }

  function loadAllocationCalendars(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    var requestId = allocationCalendarRequest + 1;
    allocationCalendarRequest = requestId;
    allocationCalendars = {};
    allocations.forEach(function (allocation) {
      allocationCalendars[allocation.id] = { state: "loading" };
    });
    refreshFocusedAllocationExperience();
    if (!allocations.length) {
      return;
    }
    Promise.all(allocations.map(function (allocation) {
      return fetch(allocationCalendarUrl + encodeURIComponent(allocation.id) + "/calendar")
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Unable to load allocation calendar.");
          }
          return response.json();
        })
        .then(function (calendar) {
          allocationCalendars[allocation.id] = { state: "ready", data: calendar };
        })
        .catch(function () {
          allocationCalendars[allocation.id] = { state: "unavailable" };
        });
    })).then(function () {
      if (requestId === allocationCalendarRequest && currentRuntime === runtime) {
        refreshFocusedAllocationExperience();
      }
    });
  }

  function selectAllocation(allocationId) {
    if (!currentRuntime || !allocationFor(allocationId)) {
      return;
    }
    focusedAllocationId = allocationId;
    refreshFocusedAllocationExperience();
  }

  function renderRuntime(runtime) {
    setSampleMode(false);
    currentRuntime = runtime;
    currentOperatingUnitName = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderPageIntro();
    renderCards(runtime);
    renderPeople(runtime);
    renderRiskLedger();
    renderDailyDirection();
    renderHomeMetrics();
    restoreConnectedRecord();
  }

  function renderRuntimeUnavailable() {
    setSampleMode(true);
    currentRuntime = sampleRuntime();
    currentPortfolio = samplePortfolio();
    currentOperatingUnitName = "Fortune Rice · Dargava, Gabhana, Aligarh";
    focusedAllocationId = null;
    allocationCalendars = {};
    renderPageIntro();
    renderCards(currentRuntime);
    renderPeople(currentRuntime);
    renderProgramme(sampleProgramme(), { state: "sample" });
    renderRiskLedger();
    renderSampleWeather();
    renderFortuneMap(sampleMap());
    renderHomeMetrics();
    restoreConnectedRecord();
  }

  function renderAudit(detail) {
    var audit = detail.audit_events || [];
    var history = audit.length ? "<ol class=\"audit-list\">" + audit.map(function (event) {
      return "<li><strong>" + escapeHtml(event.from_status) + " → " + escapeHtml(event.to_status) + "</strong>" +
        "<span>" + escapeHtml(event.actor_id) + " · " + escapeHtml(formatTime(event.created_at)) + "</span>" +
        "<span>" + escapeHtml(event.reason) + "</span></li>";
    }).join("") + "</ol>" : "<p class=\"empty-state\">No audit events recorded yet.</p>";
    setHtml("exception-detail", "<div class=\"detail-heading\"><h3>" + escapeHtml(detail.title) + "</h3>" +
      "<span class=\"status\">" + escapeHtml(detail.status) + "</span></div>" + history);
  }

  function loadException(exceptionId) {
    element("exception-detail").textContent = "Loading audit history…";
    fetch("/api/v1/exceptions/" + encodeURIComponent(exceptionId))
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load exception detail.");
        }
        return response.json();
      })
      .then(renderAudit)
      .catch(function (error) {
        element("exception-detail").textContent = error.message;
      });
  }

  function actionDestination(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type === "exception_record") {
      return { view: "farms", exceptionId: entity.id, label: "Open farm issue" };
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return { view: "settings", exceptionId: null, label: "Open data connections" };
    }
    if (entity.type === "field_information_request") {
      return { view: "inbox", exceptionId: null, label: t("openFieldAsks") };
    }
    return { view: "farms", exceptionId: null, label: "Open farm work" };
  }

  function openActionDetail(item) {
    if (!item) {
      return;
    }
    pendingAction = actionDestination(item);
    element("action-dialog-title").textContent = text(item.title);
    element("action-dialog-detail").textContent = todayDetail(item);
    element("action-dialog-next").textContent = "Next: " + todayNext(item);
    element("action-go").innerHTML = escapeHtml(pendingAction.label) +
      ' <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>';
    var dialog = element("action-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function followActionDetail() {
    if (!pendingAction) {
      return;
    }
    var action = pendingAction;
    element("action-dialog").close();
    showView(action.view);
    if (action.exceptionId) {
      loadException(action.exceptionId);
      element("audit").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    var target = action.view === "settings" ? element("context-heading") :
      (action.view === "inbox" ? element("inbox-work-heading") : element("work-heading"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function loadActionCentre() {
    element("load-status").textContent = "Loading…";
    element("portfolio-status").textContent = "Loading actions…";
    renderTodayClock();
    loadProgramme();
    fetch(dataLanesUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Weather context is unavailable.");
        }
        return response.json();
      })
      .then(renderWeatherContext)
      .catch(renderWeatherUnavailable);
    loadFortuneMap();
    fetch(runtimeUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load the current runtime.");
        }
        return response.json();
      })
      .then(function (runtime) {
        renderRuntime(runtime);
        element("load-status").textContent = "Updated just now.";
      })
      .catch(function () {
        renderRuntimeUnavailable();
        element("load-status").textContent = t("ready");
      });

    fetch(portfolioUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load portfolio context.");
        }
        return response.json();
      })
      .then(renderPortfolio)
      .catch(renderPortfolioUnavailable);

  }

  function refreshActionCentre() {
    if (!managerSessionAuthenticated) {
      loadActionCentre();
      return;
    }
    var button = element("refresh");
    button.disabled = true;
    element("load-status").textContent = "Refreshing field context…";
    fetch(trackwickRefreshUrl, { method: "POST", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Field context refresh is unavailable.");
        }
        return response.json();
      })
      .then(function () {
        loadActionCentre();
      })
      .catch(function () {
        loadActionCentre();
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".command-tab"), function (tab) {
    tab.addEventListener("click", activateView);
    tab.addEventListener("keydown", moveTab);
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-farm-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("farm", button.getAttribute("data-farm-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-farmer-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("farmer", button.getAttribute("data-farmer-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-worker-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("worker", button.getAttribute("data-worker-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-inbox-mode]"), function (button) {
    button.addEventListener("click", function () { setInboxMode(button.getAttribute("data-inbox-mode")); });
  });
  element("language-toggle").addEventListener("click", function () {
    setLocale(interfaceLocale === "en" ? "hi" : "en");
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-locale]"), function (button) {
    button.addEventListener("click", function () {
      setLocale(button.getAttribute("data-locale"));
    });
  });
  element("refresh").addEventListener("click", refreshActionCentre);
  element("manager-session-action").addEventListener("click", toggleManagerSession);
  element("close-manager-session").addEventListener("click", function () {
    element("manager-session-dialog").close();
    element("manager-session-form").reset();
    setManagerSessionFeedback("");
  });
  element("manager-session-dialog").addEventListener("cancel", function () {
    element("manager-session-form").reset();
    setManagerSessionFeedback("");
  });
  element("manager-session-form").addEventListener("submit", submitManagerSession);
  element("close-record-dialog").addEventListener("click", function () {
    element("record-dialog").close();
    updateRecordRoute(null, null);
  });
  element("record-dialog").addEventListener("cancel", function () {
    updateRecordRoute(null, null);
  });
  element("record-dialog-action").addEventListener("click", function () {
    element("record-dialog").close();
    updateRecordRoute(null, null);
    showView("inbox");
    element("ledger-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  element("inbox-filter-clear").addEventListener("click", function () {
    connectedAllocationId = null;
    updateRecordRoute(null, null);
    if (currentRuntime) {
      renderCards(currentRuntime);
    }
    renderRiskLedger();
  });
  window.addEventListener("popstate", function () {
    if (!currentRuntime) {
      return;
    }
    var dialog = element("record-dialog");
    if (dialog.open) {
      dialog.close();
    }
    restoreConnectedRecord();
    renderCards(currentRuntime);
    renderRiskLedger();
  });
  document.addEventListener("click", function (event) {
    var card = event.target.closest("[data-record-kind]");
    if (!card) {
      return;
    }
    openRecordDialog(card.getAttribute("data-record-kind"), card.getAttribute("data-record-id"));
  });
  element("review-focus").addEventListener("click", function () {
    showView(focusTargetView);
    if (focusTargetView === "farms") {
      element("allocations-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "farmers") {
      element("farmer-directory-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "workers") {
      element("worker-directory-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "inbox") {
      element("ledger-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "settings") {
      element("settings-heading").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  applyLanguage();
  renderTodayClock();
  window.setInterval(renderTodayClock, 60000);
  loadManagerSessionStatus().then(loadActionCentre);
}());
