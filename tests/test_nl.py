from __future__ import annotations

import os

import pytest

from apps.interface.nl import NaturalLanguageInterpreter


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")


@pytest.fixture
def nl() -> NaturalLanguageInterpreter:
    return NaturalLanguageInterpreter()


def test_billing_keyword_invoice(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("factura cliente Acme por 250 EUR")
    assert result["agent_name"] == "AgentBillingOps"
    assert result["action"] == "create_invoice"
    assert result["payload"]["amount_eur"] == 250.0


def test_billing_keyword_reminder(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("envia recordatorio de factura a cliente Beta")
    assert result["agent_name"] == "AgentBillingOps"
    assert result["action"] == "send_reminder"


def test_accounting_iva(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("prepara borrador de IVA para este trimestre")
    assert result["agent_name"] == "AgentAccountingAssistantES"
    assert result["action"] == "vat_draft"


def test_accounting_contabilidad(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("clasifica este asiento contable por 100 EUR")
    assert result["agent_name"] == "AgentAccountingAssistantES"


def test_delivery_incidencia(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("hay una incidencia critica en produccion")
    assert result["agent_name"] == "AgentClientDeliveryManager"
    assert result["action"] == "incident_triage"


def test_sales_lead(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("nuevo lead interesado en nuestros servicios")
    assert result["agent_name"] == "AgentSalesPipeline"


def test_sales_propuesta(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("prepara propuesta para cliente nuevo de 500 EUR")
    assert result["agent_name"] == "AgentSalesPipeline"
    assert result["action"] == "draft_proposal"


def test_compliance_rgpd(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("revisa cumplimiento RGPD de datos sensibles")
    assert result["agent_name"] == "AgentGovernanceAndCompliance"


def test_email_extracted(nl: NaturalLanguageInterpreter) -> None:
    result = nl.interpret("factura cliente Acme email acme@example.com por 100 EUR")
    assert result["payload"].get("client_email") == "acme@example.com"
