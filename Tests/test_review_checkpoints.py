from Src.agent.checkpoints import get_review_checkpoint, save_review_checkpoint


def test_review_checkpoint_is_scoped_and_updated(isolated_database) -> None:
    assert get_review_checkpoint("42", "7") is None

    save_review_checkpoint("42", "7", "sha-1")
    save_review_checkpoint("42", "8", "other-mr")
    save_review_checkpoint("43", "7", "other-project")
    save_review_checkpoint("42", "7", "sha-2")

    assert get_review_checkpoint("42", "7") == "sha-2"
    assert get_review_checkpoint("42", "8") == "other-mr"
    assert get_review_checkpoint("43", "7") == "other-project"
