(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var fortuneMapUrl = "/api/v1/fortune-map";
  var dataLanesUrl = "/api/v1/data-lanes";
  var managerSessionStatusUrl = "/api/v1/manager-session/status";
  var managerSessionLoginUrl = "/api/v1/manager-session/login";
  var managerSessionLogoutUrl = "/api/v1/manager-session/logout";
  var farmTruthRefreshUrl = "/api/v1/farm-truth/refresh";
  var farmTruthCasesUrl = "/api/v1/farm-truth/cases";
  var farmTruthDecisionPaths = {
    accept: "/accept", "needs-evidence": "/needs-evidence", reject: "/reject"
  };
  var trackwickMetricsUrl = "/api/v1/trackwick/metrics";
  var trackwickHealthUrl = "/api/v1/trackwick/health";
  var trackwickBoardUrl = "/api/v1/trackwick/board";
  var trackwickRefreshUrl = "/api/v1/trackwick/refresh";
  var currentRuntime = null;
  var currentPortfolio = null;
  var currentProgramme = null;
  var currentSourceBoard = null;
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
  var focusTargetView = "farms";
  var managerSessionAuthenticated = false;
  var farmTruthCases = [];
  var farmTruthInboxCases = [];
  var currentFarmTruthCase = null;
  var farmTruthOpenPending = false;
  var selectedFarmTruthContextKey = "";
  var farmTruthContextGeneration = 0;
  var localeStorageKey = "ffl.manager.interface-locale";
  var interfaceLocale = window.localStorage.getItem(localeStorageKey) === "hi" ? "hi" : "en";
  var copy = {
    en: {
      navHome: "Home", navFarms: "Farms", navFarmers: "Farmers", navWorkers: "Field workers", navInbox: "Inbox", navSettings: "Settings",
      refresh: "Refresh", pageTitle: "Home.", fieldPulse: "Daily direction", lastUpdate: "Last update", from: "From", weatherLoading: "Weather loading",
      sampleView: "", fortuneRice: "Fortune Rice", fortunePaddy: "Fortune paddy", indiaTime: "India Standard Time", fortuneNetwork: "Fortune network",
      localContext: "Local operating context", visitsFiled: "Visits filed", farmersOverdue: "Farmers overdue", highRiskIssues: "High-risk issues",
      farmerReach: "Farmer reach", purchaseShare: "Purchase share", chemicalRecord: "Chemical record", cropSignals: "Crop signals",
      programmeDataLoading: "Reading programme data…", noEligibleFarmers: "No kit-taking farmer records yet",
      farmerReachNote: "{recent} of {total} reached in 14 days · not crop purchase share",
      purchaseShareNote: "{purchase} qtl of {harvest} qtl reported harvest · {season}",
      chemicalRecordNote: "{count} reported · not compliance or export proof",
      cropSignalsNote: "{count} in the last {days} days · detection, not diagnosis",
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
      loading: "loading", today: "today", filedToday: "filed today", farmersNeedVisit: "farmers need a visit", highCriticalSevenDays: "high / critical · 7 days", notScheduled: "Not scheduled", notVisited: "never visited", reachedFourteenDays: "reached in 14 days", workerNoFile: "active officers did not file", unassigned: "Unassigned",
      coverageLoading: "Coverage is loading.", coverageUnavailable: "Coverage is unavailable.", dailyFilingLoading: "Daily filing is loading.", dailyFilingUnavailable: "Daily filing is unavailable.",
      mapUnavailable: "Map unavailable", noReviewedGeometry: "No reviewed geometry", reviewedField: "reviewed field", reviewedFields: "reviewed fields", mapEmpty: "No reviewed field geometry is available yet. A programme village or coverage count is never placed on this map.", mapLibraryUnavailable: "The map library is unavailable. Reviewed field geometry remains protected until the map can load.", mapManifestNote: "Map detail comes only from the latest published, reviewed farm manifest.", mapPrivacyNote: "Only manager-reviewed points and boundaries appear here. Programme coverage never becomes a farm pin.", farmMapNote: "The map uses the same reviewed farm geometry as Home.", farmMapPrivacyNote: "Only reviewed field geometry is shown. No source village is treated as a farm point.", unlockMap: "Unlock to reveal map", mapLoadFailed: "Reviewed field geometry could not be loaded right now.", mapAccessRequired: "Manager access is required before private reviewed field geometry can be shown.",
      settingsTitle: "Settings.", settingsDetail: "Access and source boundaries.", homeDetail: "What needs to move today.", farmsDetail: "Ground truth from reviewed farm and field records.", farmersDetail: "Coverage context and reviewed farmer relationships.", workersDetail: "Daily activity and reviewed ownership.", inboxDetail: "Decisions, work, and follow-through.",
      todayTitle: "Home.", farmsTitle: "Farms.", farmersTitle: "Farmers.", workersTitle: "Field workers.", inboxTitle: "Inbox.",
      openFarms: "Open farms", openFarmers: "Open farmers", openInbox: "Open inbox", openSettings: "Open settings", ready: "Ready.", loadingStatus: "Loading…", loadingActions: "Loading actions…", updatedNow: "Updated just now.", refreshingField: "Refreshing field context…", currentFieldOperations: "Current field operations",
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
      openFieldAsks: "Open field asks", noFieldRelationship: "No field relationship recorded.", fieldRelationshipPending: "Field relationship setup is pending.", fieldRelationshipUnavailable: "Field relationship summary unavailable.", noReviewedPeople: "No reviewed people records are available yet.", noReviewedFarmer: "No reviewed farmer record is available yet. Programme coverage stays separate.", noReviewedWorker: "No reviewed field worker record is available yet. Daily source activity stays aggregate until reviewed.", noActiveCrop: "No active crop allocation has been recorded yet.", addFieldAndCrop: "Add a verified field and a crop allocation to start the operating loop.", noVerifiedFields: "No verified fields yet.", farmsSummarySingle: "1 reviewed field · {location}", farmsSummaryMultiple: "{count} reviewed fields", reviewCandidates: "Review candidates", farmTruthTitle: "Review farm candidates", farmTruthLoading: "Loading candidates…", farmTruthEmpty: "No farm candidate is waiting for review.", farmTruthUnavailable: "Farm review is unavailable for the current season.", reviewSeason: "Review season", chooseReviewSeason: "Choose a season", reviewContextLabel: "{unit} · {crops}", activeSeason: "Active season", reviewRefresh: "Refresh candidates", candidateProgress: "{current} of {total}", placeFacts: "Place", areaFacts: "Area", cropFacts: "Crop and timing", visitFacts: "Visits and work", evidenceFacts: "Evidence", farmerName: "Farmer", village: "Village", block: "Block", district: "District", gataNumber: "Gata number", plotArea: "Reported plot area", registrationArea: "Reported registration area", cropStage: "Crop stage", transplantedOn: "Transplanted on", latestVisit: "Latest visit", recentVisits: "Recent visits", openFollowUps: "Open follow-ups", fieldWorkers: "Field workers", fieldName: "Field name", managedArea: "Managed area (ha)", cropName: "Crop", cultivarOptional: "Cultivar (optional)", growerEffectiveOn: "Grower effective on", rightType: "Right to operate", rightStartsOn: "Right starts on", rightEndsOn: "Right ends on", acceptCandidate: "Accept", needsEvidence: "Needs evidence", rejectCandidate: "Reject", missingEvidence: "Evidence needed", missingPlotArea: "Plot area", missingCropSeason: "Crop and season", missingRight: "Right to operate", missingFarmer: "Farmer identity", missingWorker: "Field worker assignment", reviewReason: "Reason", evidenceNeeded: "Farm Truth evidence needed", reviewSaved: "Decision saved.", reviewNext: "Opening the next candidate.", reviewFailed: "The decision could not be saved.", managerOwner: "You", bigha: "bigha", acres: "acres", actionsUnavailable: "Actions are unavailable. Home is still usable.", decisionQueueUnavailable: "The decision queue is unavailable right now.", riskActionUnavailable: "Risk and action context is unavailable right now."
    },
    hi: {
      navHome: "मुख्य", navFarms: "खेत", navFarmers: "किसान", navWorkers: "फील्ड टीम", navInbox: "इनबॉक्स", navSettings: "सेटिंग्स",
      refresh: "ताज़ा करें", pageTitle: "मुख्य।", fieldPulse: "आज की दिशा", lastUpdate: "आख़िरी अपडेट", from: "किससे", weatherLoading: "मौसम लोड हो रहा है",
      sampleView: "", fortuneRice: "फॉर्च्यून राइस", fortunePaddy: "फॉर्च्यून धान", indiaTime: "भारतीय मानक समय", fortuneNetwork: "फॉर्च्यून नेटवर्क",
      localContext: "स्थानीय परिचालन संदर्भ", visitsFiled: "दर्ज की गई मुलाक़ातें", farmersOverdue: "मुलाक़ात के लिए बाकी किसान", highRiskIssues: "उच्च जोखिम के मुद्दे",
      farmerReach: "किसान संपर्क", purchaseShare: "खरीद हिस्सेदारी", chemicalRecord: "रसायन रिकॉर्ड", cropSignals: "फसल संकेत",
      programmeDataLoading: "कार्यक्रम डेटा पढ़ा जा रहा है…", noEligibleFarmers: "किट लेने वाले किसानों का रिकॉर्ड अभी नहीं है",
      farmerReachNote: "{total} में से {recent} से 14 दिनों में संपर्क · यह फसल खरीद हिस्सेदारी नहीं है",
      purchaseShareNote: "{harvest} क्विंटल दर्ज उपज में से {purchase} क्विंटल खरीद · {season}",
      chemicalRecordNote: "{count} दर्ज · यह अनुपालन या निर्यात-तैयारी का प्रमाण नहीं है",
      cropSignalsNote: "पिछले {days} दिनों में {count} संकेत · यह पहचान है, निदान नहीं",
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
      loading: "लोड हो रहा है", today: "आज", filedToday: "आज दर्ज", farmersNeedVisit: "किसानों की मुलाक़ात बाकी", highCriticalSevenDays: "उच्च / अति गंभीर · 7 दिन", notScheduled: "निर्धारित नहीं", notVisited: "कभी मुलाक़ात नहीं हुई", reachedFourteenDays: "14 दिन में पहुँचे", workerNoFile: "सक्रिय कर्मियों ने दर्ज नहीं किया", unassigned: "जिम्मेदार तय नहीं",
      coverageLoading: "कवरेज लोड हो रहा है।", coverageUnavailable: "कवरेज उपलब्ध नहीं है।", dailyFilingLoading: "दैनिक दर्ज करना लोड हो रहा है।", dailyFilingUnavailable: "दैनिक दर्ज करना उपलब्ध नहीं है।",
      mapUnavailable: "नक्शा उपलब्ध नहीं है", noReviewedGeometry: "कोई सत्यापित ज्यामिति नहीं", reviewedField: "सत्यापित खेत", reviewedFields: "सत्यापित खेत", mapEmpty: "अभी कोई समीक्षित खेत ज्यामिति उपलब्ध नहीं है। कार्यक्रम का गांव या कवरेज संख्या इस नक्शे पर नहीं रखी जाती।", mapLibraryUnavailable: "नक्शा सेवा उपलब्ध नहीं है। समीक्षित खेत ज्यामिति नक्शा लोड होने तक सुरक्षित रहती है।", mapManifestNote: "नक्शे का विवरण केवल नवीनतम प्रकाशित, समीक्षित फार्म मैनिफेस्ट से आता है।", mapPrivacyNote: "यहाँ केवल प्रबंधक द्वारा समीक्षित बिंदु और सीमाएँ दिखाई जाती हैं। कार्यक्रम कवरेज कभी फार्म पिन नहीं बनती।", farmMapNote: "यह नक्शा मुख्य पृष्ठ वाली समीक्षित फार्म ज्यामिति ही दिखाता है।", farmMapPrivacyNote: "केवल समीक्षित खेत ज्यामिति दिखाई जाती है। किसी स्रोत गांव को फार्म बिंदु नहीं माना जाता।", unlockMap: "नक्शा देखने के लिए पहुँच खोलें", mapLoadFailed: "समीक्षित खेत ज्यामिति अभी लोड नहीं हो सकी।", mapAccessRequired: "निजी समीक्षित खेत ज्यामिति दिखाने के लिए प्रबंधक पहुँच आवश्यक है।",
      settingsTitle: "सेटिंग्स।", settingsDetail: "पहुँच और स्रोत सीमाएँ।", homeDetail: "आज क्या आगे बढ़ाना है।", farmsDetail: "समीक्षित खेत और फील्ड रिकॉर्ड से वास्तविक स्थिति।", farmersDetail: "कवरेज और समीक्षित किसान संबंध।", workersDetail: "दैनिक गतिविधि और जिम्मेदारी।", inboxDetail: "निर्णय, काम और अनुपालन।",
      todayTitle: "मुख्य।", farmsTitle: "खेत।", farmersTitle: "किसान।", workersTitle: "फील्ड कर्मी।", inboxTitle: "इनबॉक्स।",
      openFarms: "खेत खोलें", openFarmers: "किसान खोलें", openInbox: "इनबॉक्स खोलें", openSettings: "सेटिंग्स खोलें", ready: "तैयार।", loadingStatus: "लोड हो रहा है…", loadingActions: "कार्रवाइयाँ लोड हो रही हैं…", updatedNow: "अभी अपडेट हुआ।", refreshingField: "फील्ड संदर्भ ताज़ा हो रहा है…", currentFieldOperations: "वर्तमान फील्ड परिचालन",
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
      openFieldAsks: "खेत की जानकारी खोलें", noFieldRelationship: "कोई खेत संबंध दर्ज नहीं है।", fieldRelationshipPending: "खेत संबंध सेट करना बाकी है।", fieldRelationshipUnavailable: "खेत संबंध सारांश उपलब्ध नहीं है।", noReviewedPeople: "अभी कोई समीक्षित व्यक्ति रिकॉर्ड उपलब्ध नहीं है।", noReviewedFarmer: "अभी कोई समीक्षित किसान रिकॉर्ड उपलब्ध नहीं है। कार्यक्रम कवरेज अलग रहती है।", noReviewedWorker: "अभी कोई समीक्षित फील्ड कर्मी रिकॉर्ड उपलब्ध नहीं है। समीक्षा तक दैनिक स्रोत गतिविधि केवल समग्र रहती है।", noActiveCrop: "अभी कोई सक्रिय फसल आवंटन दर्ज नहीं है।", addFieldAndCrop: "परिचालन शुरू करने के लिए एक सत्यापित खेत और फसल आवंटन जोड़ें।", noVerifiedFields: "अभी कोई सत्यापित खेत नहीं है।", farmsSummarySingle: "1 समीक्षित खेत · {location}", farmsSummaryMultiple: "{count} समीक्षित खेत", reviewCandidates: "उम्मीदवारों की समीक्षा करें", farmTruthTitle: "खेत उम्मीदवारों की समीक्षा", farmTruthLoading: "उम्मीदवार लोड हो रहे हैं…", farmTruthEmpty: "समीक्षा के लिए कोई खेत उम्मीदवार बाकी नहीं है।", farmTruthUnavailable: "मौजूदा मौसम के लिए खेत समीक्षा उपलब्ध नहीं है।", reviewSeason: "समीक्षा मौसम", chooseReviewSeason: "मौसम चुनें", reviewContextLabel: "{unit} · {crops}", activeSeason: "सक्रिय मौसम", reviewRefresh: "उम्मीदवार ताज़ा करें", candidateProgress: "{total} में से {current}", placeFacts: "स्थान", areaFacts: "क्षेत्र", cropFacts: "फसल और समय", visitFacts: "मुलाक़ातें और काम", evidenceFacts: "प्रमाण", farmerName: "किसान", village: "गाँव", block: "ब्लॉक", district: "ज़िला", gataNumber: "गाटा संख्या", plotArea: "दर्ज प्लॉट क्षेत्र", registrationArea: "दर्ज पंजीकरण क्षेत्र", cropStage: "फसल अवस्था", transplantedOn: "रोपाई की तारीख", latestVisit: "नवीनतम मुलाक़ात", recentVisits: "हाल की मुलाक़ातें", openFollowUps: "खुले अनुवर्ती काम", fieldWorkers: "फील्ड कर्मी", fieldName: "खेत का नाम", managedArea: "प्रबंधित क्षेत्र (हेक्टेयर)", cropName: "फसल", cultivarOptional: "किस्म (वैकल्पिक)", growerEffectiveOn: "किसान की प्रभावी तारीख", rightType: "संचालन अधिकार", rightStartsOn: "अधिकार शुरू होने की तारीख", rightEndsOn: "अधिकार समाप्त होने की तारीख", acceptCandidate: "स्वीकार करें", needsEvidence: "प्रमाण चाहिए", rejectCandidate: "अस्वीकार करें", missingEvidence: "आवश्यक प्रमाण", missingPlotArea: "प्लॉट क्षेत्र", missingCropSeason: "फसल और मौसम", missingRight: "संचालन अधिकार", missingFarmer: "किसान की पहचान", missingWorker: "फील्ड कर्मी की जिम्मेदारी", reviewReason: "कारण", evidenceNeeded: "खेत सत्य के लिए प्रमाण चाहिए", reviewSaved: "निर्णय सहेजा गया।", reviewNext: "अगला उम्मीदवार खोला जा रहा है।", reviewFailed: "निर्णय सहेजा नहीं जा सका।", managerOwner: "आप", bigha: "बीघा", acres: "एकड़", actionsUnavailable: "कार्रवाइयाँ उपलब्ध नहीं हैं। मुख्य पृष्ठ फिर भी उपयोगी है।", decisionQueueUnavailable: "निर्णय सूची अभी उपलब्ध नहीं है।", riskActionUnavailable: "जोखिम और कार्रवाई संदर्भ अभी उपलब्ध नहीं है।"
    }
  };

  function element(id) {
    return document.getElementById(id);
  }

  function text(value) {
    return value === null || value === undefined || value === "" ? t("unassigned") : String(value);
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
    if (!managerSessionAuthenticated) {
      farmTruthInboxCases = [];
      resetFarmTruthDialogState(true);
    }
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
      .then(function () {
        loadActionCentre();
        if (farmTruthOpenPending) {
          openFarmTruthReview();
        }
      })
      .catch(function (error) {
        form.reset();
        setManagerSessionFeedback(error.message || "Manager access could not be unlocked.");
      })
      .finally(function () {
        submit.disabled = false;
        submit.textContent = t("unlockActions");
      });
  }

  function closeManagerSessionDialog() {
    farmTruthOpenPending = false;
    var dialog = element("manager-session-dialog");
    if (dialog.open) {
      dialog.close();
    }
    element("manager-session-form").reset();
    setManagerSessionFeedback("");
  }

  function toggleManagerSession() {
    if (!managerSessionAuthenticated) {
      openManagerSessionDialog();
      return;
    }
    resetFarmTruthDialogState(true);
    element("manager-session-action").disabled = true;
    fetch(managerSessionLogoutUrl, { method: "POST", credentials: "same-origin" })
      .then(function () { return loadManagerSessionStatus(); })
      .then(loadActionCentre)
      .finally(function () {
        element("manager-session-action").disabled = false;
      });
  }

  function farmTruthContexts() {
    var scope = currentPortfolio && currentPortfolio.scope;
    var activeFarms = scope && scope.active_farms && Array.isArray(scope.active_farms.items) ? scope.active_farms.items : [];
    var allocations = scope && scope.active_allocations && Array.isArray(scope.active_allocations.items) ? scope.active_allocations.items : [];
    if (!scope || scope.availability !== "available" || !activeFarms.length || !allocations.length) {
      return [];
    }
    var unitNames = {};
    activeFarms.forEach(function (unit) {
      if (unit && unit.id && unit.name) {
        unitNames[unit.id] = unit.name;
      }
    });
    var grouped = {};
    var incompleteContext = false;
    allocations.forEach(function (item) {
      if (!item || !item.operating_unit_id || !item.season_id || !unitNames[item.operating_unit_id]) {
        incompleteContext = true;
        return;
      }
      var key = item.operating_unit_id + "\u001f" + item.season_id;
      if (!grouped[key]) {
        grouped[key] = {
          key: key,
          operating_unit_id: item.operating_unit_id,
          season_id: item.season_id,
          unit_name: unitNames[item.operating_unit_id],
          crop_names: []
        };
      }
      if (item.crop_name && grouped[key].crop_names.indexOf(item.crop_name) === -1) {
        grouped[key].crop_names.push(item.crop_name);
      }
    });
    if (incompleteContext) {
      return [];
    }
    var contexts = Object.keys(grouped).sort().map(function (key) {
      var context = grouped[key];
      context.crop_names.sort();
      return {
        key: context.key,
        operating_unit_id: context.operating_unit_id,
        season_id: context.season_id,
        label: message("reviewContextLabel", {
          unit: context.unit_name,
          crops: context.crop_names.join(", ") || t("activeSeason")
        })
      };
    });
    var labelCounts = {};
    contexts.forEach(function (context) {
      labelCounts[context.label] = (labelCounts[context.label] || 0) + 1;
    });
    return contexts.some(function (context) { return labelCounts[context.label] > 1; }) ? [] : contexts;
  }

  function renderFarmTruthContextChooser() {
    var contexts = farmTruthContexts();
    var select = element("farm-truth-context");
    var existing = contexts.some(function (context) { return context.key === selectedFarmTruthContextKey; });
    var soleContext = contexts.length === 1 ? contexts.find(function () { return true; }) : null;
    if (soleContext) {
      selectedFarmTruthContextKey = soleContext.key;
    } else if (!existing) {
      selectedFarmTruthContextKey = "";
    }
    element("farm-truth-context-label").hidden = contexts.length <= 1;
    setHtml("farm-truth-context", '<option value="">' + escapeHtml(t("chooseReviewSeason")) + "</option>" + contexts.map(function (context) {
      return '<option value="' + escapeHtml(context.key) + '"' + (context.key === selectedFarmTruthContextKey ? " selected" : "") + ">" + escapeHtml(context.label) + "</option>";
    }).join(""));
    select.value = selectedFarmTruthContextKey;
    return contexts;
  }

  function farmTruthContext() {
    return farmTruthContexts().filter(function (context) {
      return context.key === selectedFarmTruthContextKey;
    })[0] || null;
  }

  function invalidateFarmTruthContext() {
    farmTruthContextGeneration += 1;
  }

  function beginFarmTruthRequest() {
    var context = farmTruthContext();
    if (!context || !element("farm-truth-dialog").open) {
      return null;
    }
    invalidateFarmTruthContext();
    return {
      context: context,
      key: context.key,
      generation: farmTruthContextGeneration
    };
  }

  function farmTruthOriginIsActive(origin) {
    var context = farmTruthContext();
    return Boolean(
      origin && element("farm-truth-dialog").open && context &&
      origin.key === selectedFarmTruthContextKey && origin.key === context.key &&
      origin.generation === farmTruthContextGeneration
    );
  }

  function farmTruthQuery(context, status) {
    return "?operating_unit_id=" + encodeURIComponent(context.operating_unit_id) +
      "&season_id=" + encodeURIComponent(context.season_id) +
      (status ? "&status=" + encodeURIComponent(status) : "");
  }

  function farmTruthResponse(response) {
    return response.json().then(function (body) {
      if (!response.ok) {
        throw new Error(t("farmTruthUnavailable"));
      }
      return body;
    });
  }

  function farmTruthDecisionResponse(response) {
    return response.json().then(function (body) {
      if (!response.ok) {
        throw new Error(t("reviewFailed"));
      }
      return body;
    });
  }

  function setFarmTruthFeedback(value, saved) {
    var feedback = element("farm-truth-feedback");
    feedback.textContent = value || "";
    feedback.hidden = !value;
    feedback.classList.toggle("is-saved", Boolean(saved));
  }

  function showFarmTruthDecisionSuccess(hasNext) {
    setFarmTruthFeedback(t("reviewSaved") + (hasNext ? " " + t("reviewNext") : ""), true);
  }

  function setFarmTruthBusy(busy) {
    element("farm-truth-refresh").disabled = busy;
    Array.prototype.forEach.call(document.querySelectorAll(".farm-truth-submit"), function (button) {
      button.disabled = busy;
    });
  }

  function farmTruthPlace(caseItem) {
    var place = caseItem && caseItem.place ? caseItem.place : {};
    return [place.village, place.block, place.district].filter(Boolean).join(" · ");
  }

  function farmTruthFact(label, value) {
    return "<div><dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(value) + "</dd></div>";
  }

  function farmTruthArea(value, unit) {
    var number = Number(value);
    return isFinite(number) && number > 0 ? formatQuantity(number) + " " + t(unit) : "—";
  }

  function renderFarmTruthList() {
    var selectedId = currentFarmTruthCase && currentFarmTruthCase.id;
    if (!farmTruthCases.length) {
      setHtml("farm-truth-list", '<p class="farm-truth-list-empty">' + escapeHtml(t("farmTruthEmpty")) + "</p>");
      element("farm-truth-progress").textContent = t("farmTruthEmpty");
      return;
    }
    var selectedIndex = farmTruthCases.map(function (item) { return item.id; }).indexOf(selectedId);
    element("farm-truth-progress").textContent = message("candidateProgress", {
      current: formatCount(selectedIndex < 0 ? 1 : selectedIndex + 1), total: formatCount(farmTruthCases.length)
    });
    setHtml("farm-truth-list", farmTruthCases.map(function (item, index) {
      var farmer = item.people ? item.people.farmer_display_name : "";
      var selected = item.id === selectedId || (!selectedId && index === 0);
      return '<button class="farm-truth-card' + (selected ? " is-selected" : "") +
        '" type="button" data-farm-truth-case="' + escapeHtml(item.id) + '" aria-pressed="' + String(selected) + '">' +
        "<strong>" + escapeHtml(farmer) + "</strong><span>" + escapeHtml(farmTruthPlace(item)) + "</span></button>";
    }).join(""));
  }

  function prefillFarmTruthAcceptance(caseItem) {
    var form = element("farm-truth-accept-form");
    form.reset();
    element("farm-truth-needs-form").reset();
    element("farm-truth-reject-form").reset();
    var place = caseItem.place || {};
    var area = caseItem.area || {};
    var registration = caseItem.registration || {};
    var fieldName = [place.village, area.gata_number ? t("gataNumber") + " " + area.gata_number : ""].filter(Boolean).join(" · ");
    form.elements.field_name.value = fieldName;
    if (Number(area.registration_plot_count) === 1 && Number(area.registration_acres) > 0) {
      form.elements.managed_area_hectares.value = (Number(area.registration_acres) * 0.404686).toFixed(2);
    }
    if (Number(registration.pb1_acres) > 0 && !Number(registration.variety_1718_acres)) {
      form.elements.cultivar.value = "PB1";
    } else if (Number(registration.variety_1718_acres) > 0 && !Number(registration.pb1_acres)) {
      form.elements.cultivar.value = "1718";
    }
  }

  function renderFarmTruthDetail() {
    var item = currentFarmTruthCase;
    renderFarmTruthList();
    if (!item) {
      setHtml("farm-truth-detail", '<p class="farm-truth-empty">' + escapeHtml(t("farmTruthEmpty")) + "</p>");
      element("farm-truth-decision-panel").hidden = true;
      return;
    }
    var place = item.place || {};
    var area = item.area || {};
    var registration = item.registration || {};
    var timing = item.crop_timing || {};
    var people = item.people || {};
    var evidence = item.evidence || {};
    var chips = (Array.isArray(evidence.reason_chips) ? evidence.reason_chips : []).concat(
      Array.isArray(evidence.safe_task_labels) ? evidence.safe_task_labels : []
    ).filter(function (chip, index, all) { return chip && all.indexOf(chip) === index; });
    var workers = Array.isArray(people.field_worker_display_names) ? people.field_worker_display_names.join(", ") : "";
    setHtml("farm-truth-detail", '<article class="farm-truth-candidate"><header><p class="eyebrow">' + escapeHtml(t("placeFacts")) +
      "</p><h3>" + escapeHtml(people.farmer_display_name) + "</h3><p>" + escapeHtml(farmTruthPlace(item)) + "</p></header>" +
      '<dl class="farm-truth-facts">' +
      farmTruthFact(t("village"), place.village) + farmTruthFact(t("block"), place.block) +
      farmTruthFact(t("district"), place.district) + farmTruthFact(t("gataNumber"), area.gata_number) +
      farmTruthFact(t("plotArea"), farmTruthArea(area.plot_bigha, "bigha")) +
      farmTruthFact(t("registrationArea"), farmTruthArea(area.registration_acres, "acres")) +
      farmTruthFact(t("cropStage"), readable(timing.crop_stage)) +
      farmTruthFact(t("transplantedOn"), timing.transplanted_on) +
      farmTruthFact(t("latestVisit"), formatTime(timing.latest_visit_at)) +
      farmTruthFact(t("recentVisits"), formatCount(evidence.recent_visit_count)) +
      farmTruthFact(t("openFollowUps"), formatCount(evidence.open_work_count)) +
      farmTruthFact(t("fieldWorkers"), workers) + "</dl>" +
      '<div class="evidence-chips" aria-label="' + escapeHtml(t("evidenceFacts")) + '">' + chips.map(function (chip) {
        return "<span>" + escapeHtml(chip) + "</span>";
      }).join("") + "</div></article>");
    element("farm-truth-decision-panel").hidden = false;
    prefillFarmTruthAcceptance(item);
  }

  function clearFarmTruthCaseState() {
    currentFarmTruthCase = null;
    farmTruthCases = [];
    element("farm-truth-progress").textContent = "";
    setHtml("farm-truth-list", "");
    setHtml("farm-truth-detail", '<p class="farm-truth-empty">' + escapeHtml(t("farmTruthUnavailable")) + "</p>");
    element("farm-truth-decision-panel").hidden = true;
    setFarmTruthBusy(false);
  }

  function renderFarmTruthUnavailable() {
    invalidateFarmTruthContext();
    clearFarmTruthCaseState();
  }

  function resetFarmTruthDialogState(clearSelection) {
    invalidateFarmTruthContext();
    if (clearSelection) {
      selectedFarmTruthContextKey = "";
    }
    setFarmTruthFeedback("");
    clearFarmTruthCaseState();
  }

  function loadFarmTruthCaseDetail(caseId) {
    var origin = arguments[1] || beginFarmTruthRequest();
    if (!origin || !caseId || !farmTruthOriginIsActive(origin)) {
      if (!origin && element("farm-truth-dialog").open) {
        renderFarmTruthUnavailable();
      }
      return Promise.resolve();
    }
    setFarmTruthBusy(true);
    return fetch(farmTruthCasesUrl + "/" + encodeURIComponent(caseId) + farmTruthQuery(origin.context), {
      credentials: "same-origin"
    }).then(farmTruthResponse).then(function (detail) {
      if (!farmTruthOriginIsActive(origin)) {
        return;
      }
      currentFarmTruthCase = detail;
      renderFarmTruthDetail();
    }).catch(function () {
      if (farmTruthOriginIsActive(origin)) {
        renderFarmTruthUnavailable();
      }
    }).finally(function () {
      if (farmTruthOriginIsActive(origin)) {
        setFarmTruthBusy(false);
      }
    });
  }

  function loadFarmTruthCases() {
    var origin = arguments[0] || beginFarmTruthRequest();
    if (!origin || !farmTruthOriginIsActive(origin)) {
      if (!origin && element("farm-truth-dialog").open) {
        renderFarmTruthUnavailable();
      }
      return Promise.resolve();
    }
    return Promise.all([
      fetch(farmTruthCasesUrl + farmTruthQuery(origin.context, "open"), { credentials: "same-origin" }).then(farmTruthResponse),
      loadFarmTruthInboxCases(origin)
    ]).then(function (results) {
      if (!farmTruthOriginIsActive(origin)) {
        return null;
      }
      farmTruthCases = Array.isArray(results[0]) ? results[0] : [];
      if (!farmTruthCases.length) {
        currentFarmTruthCase = null;
        renderFarmTruthDetail();
        return null;
      }
      return loadFarmTruthCaseDetail(farmTruthCases[0].id, origin);
    }).catch(function () {
      if (farmTruthOriginIsActive(origin)) {
        renderFarmTruthUnavailable();
      }
    });
  }

  function loadFarmTruthInboxCases() {
    var origin = arguments[0] || null;
    var contexts = farmTruthContexts();
    if (!managerSessionAuthenticated || !contexts.length) {
      farmTruthInboxCases = [];
      renderRiskLedger();
      return Promise.resolve([]);
    }
    return Promise.all(contexts.map(function (context) {
      return fetch(farmTruthCasesUrl + farmTruthQuery(context, "needs_evidence"), {
        credentials: "same-origin"
      }).then(farmTruthResponse);
    })).then(function (groups) {
      if (origin && !farmTruthOriginIsActive(origin)) {
        return [];
      }
      var known = {};
      farmTruthInboxCases = [].concat.apply([], groups).filter(function (item) {
        if (!item || item.status !== "needs_evidence" || known[item.id]) {
          return false;
        }
        known[item.id] = true;
        return true;
      });
      renderRiskLedger();
      return farmTruthInboxCases;
    }).catch(function () {
      if (origin && !farmTruthOriginIsActive(origin)) {
        return [];
      }
      farmTruthInboxCases = [];
      renderRiskLedger();
      return [];
    });
  }

  function refreshFarmTruthCases() {
    var origin = beginFarmTruthRequest();
    if (!origin) {
      if (element("farm-truth-dialog").open) {
        renderFarmTruthUnavailable();
      }
      return Promise.resolve();
    }
    setFarmTruthFeedback("");
    setFarmTruthBusy(true);
    setHtml("farm-truth-detail", '<p class="farm-truth-empty">' + escapeHtml(t("farmTruthLoading")) + "</p>");
    return fetch(farmTruthRefreshUrl, {
      method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
      body: JSON.stringify(origin.context)
    }).then(farmTruthResponse).then(function () {
      if (!farmTruthOriginIsActive(origin)) {
        return null;
      }
      return loadFarmTruthCases(origin);
    }).catch(function () {
      if (farmTruthOriginIsActive(origin)) {
        renderFarmTruthUnavailable();
      }
    }).finally(function () {
      if (farmTruthOriginIsActive(origin)) {
        setFarmTruthBusy(false);
      }
    });
  }

  function openFarmTruthReview() {
    if (!managerSessionAuthenticated) {
      farmTruthOpenPending = true;
      openManagerSessionDialog();
      return;
    }
    farmTruthOpenPending = false;
    var dialog = element("farm-truth-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
    var contexts = renderFarmTruthContextChooser();
    setFarmTruthFeedback("");
    if (contexts.length === 1) {
      refreshFarmTruthCases();
    } else {
      renderFarmTruthUnavailable();
    }
  }

  function submitFarmTruthDecision(event, decision) {
    event.preventDefault();
    var form = event.currentTarget;
    var context = farmTruthContext();
    var caseItem = currentFarmTruthCase;
    if (!context || !caseItem || !form.reportValidity()) {
      return;
    }
    var origin = beginFarmTruthRequest();
    if (!origin) {
      return;
    }
    var payload = { operating_unit_id: origin.context.operating_unit_id, season_id: origin.context.season_id };
    if (decision === "accept") {
      payload.field_name = formValue(form, "field_name");
      payload.managed_area_hectares = Number(formValue(form, "managed_area_hectares"));
      payload.crop_name = formValue(form, "crop_name");
      payload.cultivar = formValue(form, "cultivar") || null;
      payload.grower_effective_on = formValue(form, "grower_effective_on");
      payload.right_type = formValue(form, "right_type");
      payload.right_starts_on = formValue(form, "right_starts_on");
      payload.right_ends_on = formValue(form, "right_ends_on") || null;
    } else {
      payload.reason = formValue(form, "reason");
      if (decision === "needs-evidence") {
        payload.missing_evidence_kind = formValue(form, "missing_evidence_kind");
      }
    }
    setFarmTruthBusy(true);
    setFarmTruthFeedback("");
    return fetch(farmTruthCasesUrl + "/" + encodeURIComponent(caseItem.id) + farmTruthDecisionPaths[decision], {
      method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }).then(farmTruthDecisionResponse).then(function () {
      if (!farmTruthOriginIsActive(origin)) {
        return null;
      }
      if (decision === "needs-evidence") {
        farmTruthInboxCases.unshift(Object.assign({}, caseItem, {
          status: "needs_evidence", missing_evidence_kind: payload.missing_evidence_kind
        }));
      }
      farmTruthCases = farmTruthCases.filter(function (item) { return item.id !== caseItem.id; });
      currentFarmTruthCase = null;
      renderRiskLedger();
      if (!farmTruthCases.length) {
        renderFarmTruthDetail();
        showFarmTruthDecisionSuccess(false);
        return null;
      }
      return loadFarmTruthCaseDetail(farmTruthCases[0].id, origin).then(function () {
        if (farmTruthOriginIsActive(origin)) {
          showFarmTruthDecisionSuccess(true);
        }
      });
    }).catch(function () {
      if (farmTruthOriginIsActive(origin)) {
        setFarmTruthFeedback(t("reviewFailed"), false);
      }
    }).finally(function () {
      if (farmTruthOriginIsActive(origin)) {
        setFarmTruthBusy(false);
      }
    });
  }

  function setSampleMode(enabled) {
    sampleMode = Boolean(enabled);
    if (sampleMode) {
      resetFarmTruthDialogState(true);
    }
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
      outcomes: {
        farmer_reach: { recently_reached: 1585, eligible_farmers: 2592, share_percent: 61.1, window_days: 14 },
        chemical_record: { reported_events: 0, review_cues: 0 },
        crop_signals: { observations: 545, window_days: 7, lead_issue: { issue_code: "leaf folder", count: 265, highest_severity: "moderate" } },
        purchase_share: { availability: "not_connected" }
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
    var freshness = metrics && metrics.freshness ? metrics.freshness : {};
    var outcomes = metrics && metrics.outcomes ? metrics.outcomes : {};
    var sourceIsReady = freshness.status === "available";
    var farmerReach = outcomes.farmer_reach || {};
    var purchaseShare = outcomes.purchase_share || {};
    var purchaseAvailable = purchaseShare.availability === "available";
    var eligibleFarmers = firstKnownNumber([farmerReach.eligible_farmers]);
    var recentlyReached = firstKnownNumber([farmerReach.recently_reached]);
    var reachShare = firstKnownNumber([farmerReach.share_percent]);
    element("home-supply-label").textContent = purchaseAvailable ? t("purchaseShare") : t("farmerReach");
    setHomeMetric(
      "home-supply-value", "home-supply-note",
      purchaseAvailable ? formatPercent(purchaseShare.share_percent) :
        (!sourceIsReady || reachShare === null ? "—" : formatPercent(reachShare)),
      purchaseAvailable ? message("purchaseShareNote", {
        purchase: formatQuantity(purchaseShare.fortune_purchase_qtl),
        harvest: formatQuantity(purchaseShare.reported_harvest_qtl),
        season: readable(purchaseShare.season_code)
      }) : (!sourceIsReady ? t("programmeDataLoading") : (!eligibleFarmers ? t("noEligibleFarmers") :
        message("farmerReachNote", { recent: formatCount(recentlyReached), total: formatCount(eligibleFarmers) })))
    );
    var chemicalRecord = outcomes.chemical_record || {};
    var chemicalEvents = firstKnownNumber([chemicalRecord.reported_events]);
    setHomeMetric(
      "home-compliance-value", "home-compliance-note",
      !sourceIsReady || chemicalEvents === null ? "—" : formatCount(chemicalEvents),
      !sourceIsReady ? t("programmeDataLoading") :
        message("chemicalRecordNote", { count: formatCount(chemicalEvents) })
    );
    var cropSignals = outcomes.crop_signals || {};
    var observations = firstKnownNumber([cropSignals.observations]);
    var signalWindow = firstKnownNumber([cropSignals.window_days]);
    setHomeMetric(
      "home-interventions-value", "home-interventions-note",
      !sourceIsReady || observations === null ? "—" : formatCount(observations),
      !sourceIsReady ? t("programmeDataLoading") :
        message("cropSignalsNote", { count: formatCount(observations), days: formatCount(signalWindow || 7) })
    );
  }

  function formatPercent(value) {
    var numeric = Number(value);
    if (!isFinite(numeric)) {
      return "—";
    }
    return new Intl.NumberFormat(interfaceLocale === "hi" ? "hi-IN" : "en-IN", {
      maximumFractionDigits: 1
    }).format(numeric) + "%";
  }

  function formatQuantity(value) {
    var numeric = Number(value);
    if (!isFinite(numeric)) {
      return "—";
    }
    return new Intl.NumberFormat(interfaceLocale === "hi" ? "hi-IN" : "en-IN", {
      maximumFractionDigits: 1
    }).format(numeric);
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

  function renderProgrammeLocked() {
    if (sampleMode) {
      renderProgramme(sampleProgramme(), { state: "sample" });
      return;
    }
    currentProgramme = null;
    currentSourceBoard = null;
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderPeople(currentRuntime);
      renderRiskLedger();
    }
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
    currentSourceBoard = null;
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderPeople(currentRuntime);
      renderRiskLedger();
    }
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
      fetch(trackwickHealthUrl, { credentials: "same-origin" }),
      fetch(trackwickBoardUrl, { credentials: "same-origin" })
    ])
      .then(function (responses) {
        if (!responses[0].ok || !responses[1].ok || !responses[2].ok) {
          throw new Error("Programme context is unavailable.");
        }
        return Promise.all([responses[0].json(), responses[1].json(), responses[2].json()]);
      })
      .then(function (payloads) {
        renderProgramme(payloads[0], payloads[1]);
        renderSourceBoard(payloads[2]);
      })
      .catch(renderProgrammeUnavailable);
  }

  function isOpenException(exceptionRecord) {
    return ["resolved", "accepted_risk"].indexOf(exceptionRecord.status) === -1;
  }

  function isOpenWork(workItem) {
    return ["accepted", "completed", "cancelled"].indexOf(workItem.status) === -1;
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
      resetFarmTruthDialogState(true);
      if (element("farm-truth-dialog").open) {
        renderFarmTruthContextChooser();
      }
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    currentPortfolio = null;
    if (managerSessionAuthenticated) {
      loadFarmTruthInboxCases();
    }
    if (element("farm-truth-dialog").open) {
      renderFarmTruthContextChooser();
      renderFarmTruthUnavailable();
    }
    if (currentRuntime) {
      renderDailyDirection();
    }
    element("portfolio-status").textContent = t("actionsUnavailable");
    element("inbox-summary").textContent = t("decisionQueueUnavailable");
    setHtml("portfolio-ledger", '<tr><td colspan="6" class="table-empty">' + escapeHtml(t("riskActionUnavailable")) + "</td></tr>");
    renderHomeMetrics();
  }

  function inboxRows() {
    var rows = [];
    if (sourceBoardReady()) {
      rows = sourceRows("inbox").slice(0, 250).map(function (item) {
        return {
          key: "source_work_item:" + item.id,
          severity: item.status === "in_progress" ? "high" : "medium",
          title: item.task_type,
          allocationId: null,
          fieldName: item.farmer_name || t("unassigned"),
          ownerName: item.field_worker_name || t("unassigned"),
          dueAt: item.follow_up_at || item.opened_at,
          status: item.status,
          action: "review TrackWick work"
        };
      });
    } else {
      var ledger = currentPortfolio ? listedItems(currentPortfolio.risk_action_ledger) : [];
      rows = ledger.map(function (item) {
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
    }
    rows = rows.concat(farmTruthInboxRows());
    return connectedAllocationId ? rows.filter(function (row) { return row.allocationId === connectedAllocationId; }) : rows;
  }

  function farmTruthInboxRows() {
    return farmTruthInboxCases.filter(function (item) {
      return item && item.status === "needs_evidence";
    }).map(function (item) {
      return {
        key: "farm_truth:" + item.id,
        severity: "medium",
        title: t("evidenceNeeded"),
        allocationId: null,
        fieldName: farmTruthPlace(item) || t("unassigned"),
        ownerName: t("managerOwner"),
        dueAt: null,
        status: "needs_evidence",
        action: readable(item.missing_evidence_kind)
      };
    });
  }

  function renderRiskLedger() {
    var rows = inboxRows();
    var sourceWork = sourceBoardReady();
    var selectedAllocation = sourceWork ? null : (connectedAllocationId ? allocationFor(connectedAllocationId) : null);
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
    var summary = sourceWork ? formatCount(rows.length) + " open field items · highest-attention first." : (currentInboxMode === "all" ?
      message("allDecisions", { count: formatCount(rows.length) }) :
      message(rows.length === 1 ? "priorityDecision" : "priorityDecisions", { count: formatCount(rows.length) }));
    element("inbox-summary").textContent = selectedAllocation ?
      message("decisionsForField", { field: fieldLabel(selectedAllocation.operational_block_name) }) + " · " + summary : summary;
    setHtml("portfolio-ledger", rows.map(function (item) {
      return '<tr><td><span class="severity severity-' + escapeHtml(item.severity) + '">' + escapeHtml(readable(item.severity)) +
        '</span></td><th scope="row">' + escapeHtml(sampleText(item.title)) + '</th><td>' + escapeHtml(item.fieldName || fieldNameFor(item.allocationId)) +
        '</td><td>' + escapeHtml(item.ownerName || personName(item.ownerId)) + '</td><td>' + escapeHtml(formatTime(item.dueAt)) +
        '</td><td><span class="status">' + escapeHtml(readable(item.status)) + '</span></td></tr>';
    }).join(""));
    renderHomeMetrics();
  }

  function renderPortfolio(portfolio) {
    if (!portfolio || typeof portfolio !== "object") {
      renderPortfolioUnavailable();
      return;
    }
    if (sampleMode && !listedItems(portfolio.risk_action_ledger).length) {
      currentPortfolio = samplePortfolio();
      resetFarmTruthDialogState(true);
      if (element("farm-truth-dialog").open) {
        renderFarmTruthContextChooser();
      }
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    var previousFarmTruthContextKey = selectedFarmTruthContextKey;
    currentPortfolio = portfolio;
    if (managerSessionAuthenticated) {
      loadFarmTruthInboxCases();
    }
    if (element("farm-truth-dialog").open) {
      renderFarmTruthContextChooser();
      if (!selectedFarmTruthContextKey || selectedFarmTruthContextKey !== previousFarmTruthContextKey) {
        setFarmTruthFeedback("");
        renderFarmTruthUnavailable();
      }
    }
    if (currentRuntime) {
      renderDailyDirection();
    }
    renderRiskLedger();
    element("portfolio-status").textContent = t("updatedNow");
    renderHomeMetrics();
  }

  function sourceBoardReady() {
    return Boolean(currentSourceBoard && currentSourceBoard.source && currentSourceBoard.source.state === "succeeded");
  }

  function sourceRows(kind) {
    return sourceBoardReady() && Array.isArray(currentSourceBoard[kind]) ? currentSourceBoard[kind] : [];
  }

  function sourceFarmFor(id) {
    return sourceRows("farms").filter(function (farm) { return farm.id === id; })[0] || null;
  }

  function sourceFarmerFor(id) {
    return sourceRows("farmers").filter(function (farmer) { return farmer.id === id; })[0] || null;
  }

  function sourceWorkerFor(id) {
    return sourceRows("field_workers").filter(function (worker) { return worker.id === id; })[0] || null;
  }

  function sourceFarmCardMarkup(farm) {
    var hasArea = Number(farm.reported_area_acres) > 0;
    var traits = [
      farm.place,
      Number(farm.pb1_area_acres) > 0 ? "PB-1 · " + formatQuantity(farm.pb1_area_acres) + " ac" : "",
      farm.open_work ? formatCount(farm.open_work) + " " + t("openWork") : "",
      farm.crop_photo_references ? formatCount(farm.crop_photo_references) + " crop photo references" : ""
    ].filter(Boolean);
    return '<button class="directory-card allocation-card" type="button" data-record-kind="farm" data-record-id="' + escapeHtml(farm.id) + '">' +
      '<div class="allocation-card-heading"><h3>' + escapeHtml(farm.farmer_name) + '</h3><span class="status">' + escapeHtml(t("reported")) + '</span></div>' +
      '<p class="allocation-crop">' + escapeHtml(farm.place) + '</p>' +
      '<div class="directory-card-metric"><strong>' + escapeHtml(hasArea ? formatQuantity(farm.reported_area_acres) + " ac" : formatCount(farm.open_work)) +
      '</strong><span>' + escapeHtml(hasArea ? t("area") : t("openWork")) + '</span></div>' +
      '<ul class="directory-characteristics">' + traits.map(function (trait) { return '<li>' + escapeHtml(trait) + '</li>'; }).join("") + '</ul></button>';
  }

  function sourceFarmTableMarkup(farms) {
    if (!farms.length) {
      return '<tr><td colspan="4" class="table-empty">No reported farm candidates yet.</td></tr>';
    }
    return farms.map(function (farm) {
      return '<tr><th scope="row">' + escapeHtml(farm.farmer_name) + '</th><td>' + escapeHtml(farm.place) +
        '</td><td>' + escapeHtml(Number(farm.reported_area_acres) > 0 ? formatQuantity(farm.reported_area_acres) + " ac" : "—") +
        '</td><td><span class="status">' + escapeHtml(t("reported")) + '</span></td></tr>';
    }).join("");
  }

  function renderSourceFarms() {
    var farms = sourceRows("farms").slice(0, 150);
    if (!farms.length) {
      return false;
    }
    var counts = currentSourceBoard.counts || {};
    element("allocation-summary").textContent = formatCount(counts.farm_candidates) + " reported farm candidates · showing the highest-attention records first.";
    setHtml("allocation-list", farms.map(sourceFarmCardMarkup).join(""));
    setHtml("farm-table-body", sourceFarmTableMarkup(farms));
    return true;
  }

  function renderAllocationCards(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    if (!allocations.length) {
      element("allocation-summary").textContent = t("noActiveCrop");
      setHtml("allocation-list", '<p class="empty-state">' + escapeHtml(t("addFieldAndCrop")) + "</p>");
      setHtml("farm-table-body", '<tr><td colspan="4" class="table-empty">' + escapeHtml(t("noVerifiedFields")) + "</td></tr>");
      return;
    }
    element("allocation-summary").textContent = allocations.length === 1 ?
      message("farmsSummarySingle", { location: allocations[0].location_label || allocations[0].operational_block_name || t("reviewedField") }) :
      message("farmsSummaryMultiple", { count: formatCount(allocations.length) });
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
      clearLeafletMap(containerId, t("mapEmpty"));
      return;
    }
    var container = element(containerId);
    if (!window.L) {
      clearLeafletMap(containerId, t("mapLibraryUnavailable"));
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
      style: function () {
        return { color: "#bc7a1e", weight: 2, fillColor: "#d8b14d", fillOpacity: 0.28 };
      },
      pointToLayer: function (_feature, latlng) {
        return window.L.circleMarker(latlng, {
          radius: 7, color: "#173f2c", weight: 2,
          fillColor: "#d7aa3f", fillOpacity: 0.95
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
    renderBestMap();
  }

  function renderBestMap() {
    var reviewed = currentFortuneMap && Array.isArray(currentFortuneMap.features) ? currentFortuneMap.features : [];
    var count = reviewed.length;
    element("home-map-status").textContent = count ? formatCount(count) + " " +
      (count === 1 ? t("reviewedField") : t("reviewedFields")) : t("noReviewedGeometry");
    element("home-map-note").textContent = count ? t("mapManifestNote") : t("mapPrivacyNote");
    element("farm-map-note").textContent = count ? t("farmMapNote") : t("farmMapPrivacyNote");
    var manifest = { type: "FeatureCollection", features: reviewed };
    renderMapCanvas("home-map-canvas", manifest);
    renderMapCanvas("farm-map-canvas", manifest);
  }

  function renderFortuneMapUnavailable() {
    currentFortuneMap = { type: "FeatureCollection", features: [] };
    element("home-map-status").textContent = t("noReviewedGeometry");
    element("home-map-note").textContent = managerSessionAuthenticated ?
      t("mapLoadFailed") : t("mapAccessRequired");
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
    return person ? person.name : t("unassigned");
  }

  function allocationFor(allocationId) {
    var allocations = currentRuntime && Array.isArray(currentRuntime.allocations) ? currentRuntime.allocations : [];
    return allocations.filter(function (allocation) { return allocation.id === allocationId; })[0] || null;
  }

  function fieldNameFor(allocationId) {
    var allocation = allocationFor(allocationId);
    return allocation && allocation.operational_block_name ? fieldLabel(allocation.operational_block_name) : t("field");
  }

  function setFocusAction(label, targetView) {
    focusTargetView = targetView;
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
    }).join(" · ") : (relationshipAvailability === "available" ? t("noFieldRelationship") :
      (relationshipAvailability === "not_configured" ? t("fieldRelationshipPending") : t("fieldRelationshipUnavailable")));
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
      return '<tr><td colspan="4" class="table-empty">' + escapeHtml(t("noReviewedPeople")) + "</td></tr>";
    }
    return people.map(function (person) {
      return '<tr><th scope="row">' + escapeHtml(person.name) + '</th><td>' + escapeHtml(person.role) +
        '</td><td>' + escapeHtml(person.scope) + '</td><td>' + escapeHtml(formatCount(person.openWork) + " " + (person.openWork === 1 ? t("openAction") : t("openActions"))) +
        '</td></tr>';
    }).join("");
  }

  function sourcePersonCardMarkup(person, kind) {
    var isFarmer = kind === "farmer";
    var hasArea = isFarmer && Number(person.reported_area_acres) > 0;
    var metric = hasArea ? formatQuantity(person.reported_area_acres) + " ac" : formatCount(person.open_work || person.completed_work || 0);
    var metricLabel = hasArea ? t("area") : (isFarmer ? t("openWork") : t("openWork"));
    var characteristics = isFarmer ? [
      person.crm_status ? readable(person.crm_status) : "",
      person.tag ? person.tag : "",
      formatCount(person.farm_candidates) + " reported farms",
      person.crop_photo_references ? formatCount(person.crop_photo_references) + " crop photo references" : ""
    ] : [
      formatCount(person.completed_work) + " completed",
      person.latest_attendance && person.latest_attendance.status ? readable(person.latest_attendance.status) : "",
      person.latest_attendance && person.latest_attendance.observed_on ? person.latest_attendance.observed_on : ""
    ];
    return '<button class="directory-card person-card" type="button" data-record-kind="' + kind + '" data-record-id="' + escapeHtml(person.id) + '">' +
      '<h3>' + escapeHtml(person.name) + '</h3><p class="person-role">' + escapeHtml(isFarmer ? t("farmer") : t("fieldWorker")) + '</p>' +
      '<div class="directory-card-metric"><strong>' + escapeHtml(metric) + '</strong><span>' + escapeHtml(metricLabel) + '</span></div>' +
      '<ul class="directory-characteristics">' + characteristics.filter(Boolean).map(function (trait) { return '<li>' + escapeHtml(trait) + '</li>'; }).join("") + '</ul></button>';
  }

  function sourcePeopleTableMarkup(people, kind) {
    if (!people.length) {
      return '<tr><td colspan="4" class="table-empty">No source records yet.</td></tr>';
    }
    return people.map(function (person) {
      var scope = kind === "farmer" ? formatCount(person.farm_candidates) + " reported farms" : formatCount(person.completed_work) + " completed";
      return '<tr><th scope="row">' + escapeHtml(person.name) + '</th><td>' + escapeHtml(kind === "farmer" ? t("farmer") : t("fieldWorker")) +
        '</td><td>' + escapeHtml(scope) + '</td><td>' + escapeHtml(formatCount(person.open_work || 0)) + '</td></tr>';
    }).join("");
  }

  function renderSourcePeople() {
    var farmers = sourceRows("farmers").slice(0, 150);
    var workers = sourceRows("field_workers").slice(0, 150);
    if (!farmers.length && !workers.length) {
      return false;
    }
    setHtml("farmer-list", farmers.map(function (farmer) { return sourcePersonCardMarkup(farmer, "farmer"); }).join(""));
    setHtml("worker-list", workers.map(function (worker) { return sourcePersonCardMarkup(worker, "worker"); }).join(""));
    setHtml("farmer-table-body", sourcePeopleTableMarkup(farmers, "farmer"));
    setHtml("worker-table-body", sourcePeopleTableMarkup(workers, "worker"));
    return true;
  }

  function renderSourceBoard(board) {
    currentSourceBoard = board && typeof board === "object" ? board : null;
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderPeople(currentRuntime);
    }
    renderRiskLedger();
    renderBestMap();
  }

  function renderPeople(runtime) {
    if (renderSourcePeople()) {
      return;
    }
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
      '<p class="empty-state">' + escapeHtml(t("noReviewedFarmer")) + "</p>");
    setHtml("worker-list", workers.length ? workers.map(personCardMarkup).join("") :
      '<p class="empty-state">' + escapeHtml(t("noReviewedWorker")) + "</p>");
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
      var sourceFarm = sourceFarmFor(id);
      if (sourceFarm) {
        title = sourceFarm.farmer_name;
        metric = Number(sourceFarm.reported_area_acres) > 0 ? formatQuantity(sourceFarm.reported_area_acres) + " ac" : formatCount(sourceFarm.open_work);
        metricLabel = Number(sourceFarm.reported_area_acres) > 0 ? t("area") : t("openWork");
        traits = [
          sourceFarm.place,
          sourceFarm.reported_plot_count ? formatCount(sourceFarm.reported_plot_count) + " reported plots" : "",
          Number(sourceFarm.pb1_area_acres) > 0 ? "PB-1 · " + formatQuantity(sourceFarm.pb1_area_acres) + " ac" : "",
          sourceFarm.open_work ? formatCount(sourceFarm.open_work) + " " + t("openWork") : "",
          sourceFarm.crop_photo_references ? formatCount(sourceFarm.crop_photo_references) + " crop photo references" : ""
        ];
        context = "Reported farm candidate · requires Fortune review";
      } else {
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
      }
    } else {
      var sourcePerson = kind === "farmer" ? sourceFarmerFor(id) : sourceWorkerFor(id);
      if (sourcePerson) {
        var sourceFarmer = kind === "farmer";
        title = sourcePerson.name;
        metric = sourceFarmer && Number(sourcePerson.reported_area_acres) > 0 ? formatQuantity(sourcePerson.reported_area_acres) + " ac" : formatCount(sourcePerson.open_work || sourcePerson.completed_work || 0);
        metricLabel = sourceFarmer && Number(sourcePerson.reported_area_acres) > 0 ? t("area") : t("openWork");
        traits = sourceFarmer ? [
          sourcePerson.crm_status ? readable(sourcePerson.crm_status) : "",
          sourcePerson.tag || "",
          formatCount(sourcePerson.farm_candidates) + " reported farms",
          sourcePerson.crop_photo_references ? formatCount(sourcePerson.crop_photo_references) + " crop photo references" : ""
        ] : [
          formatCount(sourcePerson.completed_work) + " completed",
          sourcePerson.latest_attendance && sourcePerson.latest_attendance.status ? readable(sourcePerson.latest_attendance.status) : "",
          sourcePerson.latest_attendance && sourcePerson.latest_attendance.observed_on ? sourcePerson.latest_attendance.observed_on : ""
        ];
        context = sourceFarmer ? "TrackWick farmer record" : "TrackWick field-worker record";
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
    }
    element("record-dialog-kind").textContent = kind === "farm" ? t("field") : (kind === "farmer" ? t("farmer") : t("fieldWorker"));
    element("record-dialog-title").textContent = title;
    element("record-dialog-metric").textContent = metric;
    element("record-dialog-metric-label").textContent = metricLabel;
    element("record-dialog-context").textContent = context;
    recordTraits(traits);
    var action = element("record-dialog-action");
    action.hidden = kind !== "farm" || Boolean(sourceFarmFor(id));
    action.textContent = kind === "farm" && !sourceFarmFor(id) ? t("viewRelatedDecisions") : "";
    if (syncRoute !== false) {
      updateRecordRoute(kind, id);
    }
    var dialog = element("record-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function setDailyDirection(status, title, note, targetView) {
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
    setFocusAction(labels[targetView] || t("navHome"), targetView);
  }

  function renderDailyDirection() {
    var programme = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!programme) {
      setDailyDirection(
        "reading", t("directionLoadingTitle"),
        t("directionLoadingNote"), "workers"
      );
      return;
    }
    var visits = programme.visits || {};
    var coverage = programme.coverage || {};
    var issues = programme.issues || {};
    var issueRows = Array.isArray(issues.by_issue) ? issues.by_issue : [];
    var officersWithoutVisit = Number(visits.active_officers_without_filed_visit) || 0;
    var activeOfficers = Number(visits.active_officers) || 0;
    var filedToday = Number(visits.filed_on_reporting_day) || 0;
    var filingOfficers = Number(visits.filing_officers) || 0;
    var overdue = Number(coverage.overdue) || 0;
    var urgentIssue = issueRows.filter(function (issue) {
      return ["critical", "high"].indexOf(issue.highest_severity) !== -1;
    })[0] || null;
    if (urgentIssue) {
      setDailyDirection(
        "attention", message("cropInterventionTitle", { issue: readable(urgentIssue.issue_code) }),
        message("cropInterventionNote", { count: formatCount(urgentIssue.count), days: formatCount(issues.window_days || 7) }),
        "inbox"
      );
      return;
    }
    if (officersWithoutVisit > 0) {
      setDailyDirection(
        "attention", t("coverageRiskTitle"),
        message("coverageRiskNote", { filed: formatCount(filedToday), filing: formatCount(filingOfficers), active: formatCount(activeOfficers) }),
        "workers"
      );
      return;
    }
    setDailyDirection(
      overdue ? "attention" : "reported", overdue ? t("coverageRepairTitle") : t("farmerCoverageCurrent"),
      overdue ? t("farmerOverdueNote") : t("noOverdueNote"),
      "farmers"
    );
  }

  function renderRuntime(runtime) {
    setSampleMode(false);
    currentRuntime = runtime;
    currentOperatingUnitName = runtime.operating_unit ? runtime.operating_unit.name : t("currentFieldOperations");
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
    renderPageIntro();
    renderCards(currentRuntime);
    renderPeople(currentRuntime);
    renderProgramme(sampleProgramme(), { state: "sample" });
    renderRiskLedger();
    renderSampleWeather();
    renderFortuneMapUnavailable();
    renderHomeMetrics();
    restoreConnectedRecord();
  }

  function loadActionCentre() {
    element("load-status").textContent = t("loadingStatus");
    element("portfolio-status").textContent = t("loadingActions");
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
        element("load-status").textContent = t("updatedNow");
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
    element("load-status").textContent = t("refreshingField");
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
  element("farm-truth-open").addEventListener("click", openFarmTruthReview);
  element("farm-truth-refresh").addEventListener("click", refreshFarmTruthCases);
  element("close-farm-truth").addEventListener("click", function () {
    element("farm-truth-dialog").close();
    resetFarmTruthDialogState(true);
  });
  element("farm-truth-dialog").addEventListener("cancel", function () {
    resetFarmTruthDialogState(true);
  });
  element("farm-truth-context").addEventListener("change", function (event) {
    resetFarmTruthDialogState(true);
    selectedFarmTruthContextKey = event.currentTarget.value;
    if (selectedFarmTruthContextKey) {
      loadFarmTruthCases().catch(renderFarmTruthUnavailable);
    } else {
      renderFarmTruthUnavailable();
    }
  });
  element("farm-truth-list").addEventListener("click", function (event) {
    var card = event.target.closest("[data-farm-truth-case]");
    if (card) {
      setFarmTruthFeedback("");
      loadFarmTruthCaseDetail(card.getAttribute("data-farm-truth-case"));
    }
  });
  element("farm-truth-accept-form").addEventListener("submit", function (event) {
    submitFarmTruthDecision(event, "accept");
  });
  element("farm-truth-needs-form").addEventListener("submit", function (event) {
    submitFarmTruthDecision(event, "needs-evidence");
  });
  element("farm-truth-reject-form").addEventListener("submit", function (event) {
    submitFarmTruthDecision(event, "reject");
  });
  element("manager-session-action").addEventListener("click", toggleManagerSession);
  element("close-manager-session").addEventListener("click", function () {
    closeManagerSessionDialog();
  });
  element("manager-session-dialog").addEventListener("cancel", function (event) {
    event.preventDefault();
    closeManagerSessionDialog();
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
