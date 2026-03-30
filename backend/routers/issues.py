import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import get_all_weeks, get_issue_by_id, get_issues_by_week, get_latest_week
from models import IssueListResponse, IssuePackage, TrackType, WeeksResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["issues"])


@router.get("/weeks", response_model=WeeksResponse, response_model_by_alias=True)
async def get_weeks():
    """
    Return all available week dates in descending order.
    Each week_date is the Monday of that week (YYYY-MM-DD).
    """
    weeks = await get_all_weeks()
    return WeeksResponse(weeks=weeks, total=len(weeks))


@router.get("/issues/latest", response_model=IssueListResponse, response_model_by_alias=True)
async def get_latest_issues(
    track: Optional[str] = Query(
        None,
        description="Filter by track: 인문사회, 자연공학, 의약생명",
    )
):
    """
    Return issues from the most recent week.
    Optionally filter by track.
    """
    latest_week = await get_latest_week()
    if latest_week is None:
        return IssueListResponse(issues=[], total=0, week_date=None)

    # Validate track if provided
    if track:
        valid_tracks = [t.value for t in TrackType]
        if track not in valid_tracks:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid track '{track}'. Must be one of: {valid_tracks}",
            )

    issues = await get_issues_by_week(week_date=latest_week, track=track)
    return IssueListResponse(
        issues=issues,
        total=len(issues),
        week_date=latest_week,
    )


@router.get("/issues", response_model=IssueListResponse, response_model_by_alias=True)
async def get_issues(
    week: Optional[str] = Query(
        None,
        description="Week date in YYYY-MM-DD format (Monday of the week). Defaults to latest week.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    track: Optional[str] = Query(
        None,
        description="Filter by track: 인문사회, 자연공학, 의약생명",
    ),
):
    """
    Return issues for a specific week, optionally filtered by track.
    If no week is specified, returns the latest week's issues.
    """
    # Validate track if provided
    if track:
        valid_tracks = [t.value for t in TrackType]
        if track not in valid_tracks:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid track '{track}'. Must be one of: {valid_tracks}",
            )

    issues = await get_issues_by_week(week_date=week, track=track)

    # Determine the actual week_date used
    actual_week = week
    if actual_week is None and issues:
        actual_week = issues[0].week_date

    return IssueListResponse(
        issues=issues,
        total=len(issues),
        week_date=actual_week,
    )


@router.get("/issues/{issue_id}", response_model=IssuePackage, response_model_by_alias=True)
async def get_issue(issue_id: str):
    """
    Return full details of a single issue by its ID.
    """
    issue = await get_issue_by_id(issue_id)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=f"Issue with id '{issue_id}' not found",
        )
    return issue
