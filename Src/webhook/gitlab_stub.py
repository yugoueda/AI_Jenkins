import logging


async def post_comment(mr_id: str, message: str) -> None:
    logging.info("GitLab comment stub: mr=%s message=%s", mr_id, message)


async def all_discussions_resolved(project_id: str, mr_id: str) -> bool:
    logging.info("GitLab discussions stub: project=%s mr=%s", project_id, mr_id)
    return True
