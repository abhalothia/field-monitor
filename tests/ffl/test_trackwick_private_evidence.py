from datetime import datetime

from ffl.integrations.trackolap.trackwick import (
    TrackwickApiConfig,
    TrackwickFetchResult,
    _safe_remote_trackwick_url,
    normalise_trackwick_private_evidence,
)


CONFIG = TrackwickApiConfig(
    customer_id="trackwick-tenant",
    tenant_id="fortune-paddy",
    api_key_reference="env://FFL_TRACKWICK_API_KEY",
)


def test_private_evidence_normaliser_admits_only_typed_spatial_and_media_evidence():
    fetched = TrackwickFetchResult(
        tasks=(
            {
                "id": "visit-1",
                "type": "Farmer Visit",
                "status": "Completed",
                "customerIden": "farmer-1",
                "customerName": "Fortune Farmer",
                "employeeIden": "worker-1",
                "assignedTo": "Field Worker",
                "created": 1785750000000,
                "completed": 1785751200000,
                "completeGeo": {
                    "lat": 27.95,
                    "lng": 78.27,
                    "address": "Dargava",
                    "inGeoDetail": "provider precise address",
                },
                "formDetails": {
                    "स्थान": {
                        "lat": 27.951,
                        "lng": 78.271,
                        "address": "Visit point",
                        "geoAddress": "Visit geo address",
                    },
                    "रोपाई की तारीख (Date of transplanting)": "03-08-2026",
                    "फसल की अवस्था": "Tillering",
                    "खेत में पानी की स्थिति": "Good",
                    "फसल की स्थिति (1 = बहुत खराब | 10 = बहुत अच्छी )": "8",
                    "क्या किसान ने किट ले ली है?": "Yes",
                    "क्या फसल में कोई कीट है ?": ["Stem Borer"],
                    "जिस कीटनाशक (Pesticide) का छिड़काव किया गया है , सूची में उसका चयन करें ?": ["Product A"],
                    "कृपया उस उर्वरक (Fertilizer) का चयन करें, जिसका सुझाव आपने किसानों को दिया है।": ["Product F"],
                    "फसल की फोटो": {
                        "url": "https://trackolap-images-prod.s3.amazonaws.com/crop-1.jpg",
                        "createdOn": 1785751200000,
                        "geo": {"lat": 27.952, "lng": 78.272},
                    },
                    "Comment": "Never persist free text",
                },
            },
            {
                "id": "registration-1",
                "type": "New Farmer Registration",
                "status": "Completed",
                "customerIden": "farmer-1",
                "employeeIden": "worker-1",
                "created": 1785750000000,
                "completed": 1785751200000,
                "formDetails": {
                    "Village": "Dargava",
                    "Block": "Gabhana",
                    "District": "Aligarh",
                    "Total Acre": "5.5",
                    "Number of Plots": "1",
                    "P.B-1 Acre": "3",
                    "1718 Acre": "2.5",
                    "Mobile No": "9999999999",
                    "Geo": {"lat": 27.953, "lng": 78.273, "address": "Registration point"},
                    "Plot Details": [{
                        "Gata No.": "123",
                        "Plot Size (Bigha)": "2.5",
                        "Plot Type": "Irrigated",
                        "Village": "Dargava",
                        "Father Name": "Never persist",
                        "Land Owner Name": "Never persist",
                    }],
                    "Aadhar No": "111122223333",
                    "Aadhar Card Photo": {"url": "https://trackolap-images-prod.s3.amazonaws.com/aadhaar.jpg"},
                    "Farmer Signature": "Never persist",
                },
            },
        ),
        customers=(
            {
                "iden": "farmer-1",
                "name": "Fortune Farmer",
                "mobile": "9999999999",
                "owner": "worker-1",
                "status": "ACTIVE",
                "tag": "PB1",
                "createdOn": 1785750000000,
            },
        ),
        attendance=(
            {
                "empId": "worker-1",
                "name": "Field Worker",
                "date": "2026-08-03",
                "startTime": "09:00",
                "totalTime": "08:00",
            },
        ),
        task_pages=1,
        customer_pages=1,
    )

    result = normalise_trackwick_private_evidence(
        fetched,
        CONFIG,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    by_table = result.records_by_table()
    assert result.quarantined_rows == 0
    assert len(by_table["trackwick_parties"]) == 2
    assert len(by_table["trackwick_contact_points"]) == 1
    assert len(by_table["trackwick_tasks"]) == 2
    assert len(by_table["trackwick_visits"]) == 1
    assert len(by_table["trackwick_visit_findings"]) == 1
    assert len(by_table["trackwick_crop_inputs"]) == 2
    assert len(by_table["trackwick_registrations"]) == 1
    assert len(by_table["trackwick_registration_plots"]) == 1
    assert len(by_table["trackwick_media_references"]) == 1
    assert len(by_table["trackwick_location_observations"]) == 4
    assert len(by_table["trackwick_worker_days"]) == 1

    visit = by_table["trackwick_visits"][0].values
    assert visit["transplanted_on"] == "2026-08-03"
    assert visit["crop_condition_score"] == 8.0
    assert {row.values["input_kind"] for row in by_table["trackwick_crop_inputs"]} == {"pesticide", "fertilizer"}
    assert {row.values["location_kind"] for row in by_table["trackwick_location_observations"]} == {
        "task_completion", "visit_location", "registration", "media_capture"
    }

    serialized = repr(result)
    for forbidden in ("111122223333", "aadhaar.jpg", "Never persist", "provider precise address"):
        assert forbidden not in serialized


def test_private_evidence_normaliser_rejects_unapproved_media_hosts_and_invalid_coordinates():
    fetched = TrackwickFetchResult(
        tasks=(
            {
                "id": "visit-1",
                "type": "Farmer Visit",
                "status": "Completed",
                "customerIden": "farmer-1",
                "created": 1785750000000,
                "completed": 1785751200000,
                "completeGeo": {"lat": 127.95, "lng": 78.27},
                "formDetails": {
                    "फसल की फोटो": {"url": "https://provider.example/crop.jpg"},
                },
            },
        ),
        attendance=(),
        task_pages=1,
    )

    result = normalise_trackwick_private_evidence(
        fetched,
        CONFIG,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    by_table = result.records_by_table()
    assert result.quarantined_rows == 0
    assert by_table["trackwick_tasks"]
    assert "trackwick_media_references" not in by_table
    assert "trackwick_location_observations" not in by_table


def test_private_evidence_normaliser_accepts_a_plot_photo_only_when_its_exact_label_is_configured():
    config = TrackwickApiConfig(
        customer_id="trackwick-tenant",
        tenant_id="fortune-paddy",
        api_key_reference="env://FFL_TRACKWICK_API_KEY",
        plot_photo_form_key="Largest plot photo",
    )
    fetched = TrackwickFetchResult(
        tasks=(
            {
                "id": "early-field-1",
                "type": "Early Field Visit Form",
                "status": "Completed",
                "created": 1785750000000,
                "completed": 1785751200000,
                "formDetails": {
                    "Largest plot photo": [{
                        "url": "https://trackolap-images-prod.s3.amazonaws.com/plot-1.jpg",
                        "createdOn": 1785751200000,
                        "geo": {"lat": 27.952, "lng": 78.272},
                    }],
                    "Aadhar Card Photo": {"url": "https://trackolap-images-prod.s3.amazonaws.com/aadhaar.jpg"},
                },
            },
        ),
        attendance=(),
        task_pages=1,
    )

    result = normalise_trackwick_private_evidence(
        fetched,
        config,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    by_table = result.records_by_table()
    assert [row.values["media_kind"] for row in by_table["trackwick_media_references"]] == ["plot_photo"]
    assert "aadhaar.jpg" not in repr(result)


def test_private_media_url_canonicalises_only_the_same_approved_s3_origin():
    assert _safe_remote_trackwick_url(
        "https://TRACKOLAP-IMAGES-PROD.s3.amazonaws.com:443/crop.jpg?signature=kept"
    ) == "https://trackolap-images-prod.s3.amazonaws.com/crop.jpg?signature=kept"
    assert _safe_remote_trackwick_url(
        "https://trackolap-images-prod.s3.amazonaws.com:8443/crop.jpg"
    ) is None
    assert _safe_remote_trackwick_url(
        "https://trackolap-images-prod.s3.amazonaws.com.evil.example/crop.jpg"
    ) is None
