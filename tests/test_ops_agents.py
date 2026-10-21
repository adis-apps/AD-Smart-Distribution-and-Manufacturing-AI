from app.ops_agents import edi_exceptions, validate_transaction, supply_reconcile, draft_action


def test_edi_precheck_flags_bad_documents_and_keeps_clean_docs():
    docs = edi_exceptions()
    assert len(docs) == 30
    assert any(not d['precheck_valid'] for d in docs)
    assert any(d['precheck_valid'] for d in docs)
    assert all('recommended_action' in d for d in docs)


def test_edi_validation_returns_none_for_unknown_transaction():
    assert validate_transaction('NO-SUCH-EDI') is None


def test_supply_reconciliation_has_actionable_statuses():
    rows = supply_reconcile()
    assert rows
    assert all(r['status'] in {'Shortage Risk', 'Balanced', 'Potential Excess'} for r in rows)
    assert all(r['recommended_actions'] for r in rows)


def test_actions_are_drafts_only():
    result = draft_action('Test Agent', 'TEST-1', 'Test action', 'Review before applying')
    assert result['saved'] is True
    assert result['status'] == 'Draft'
    assert 'nothing was transmitted' in result['message']
