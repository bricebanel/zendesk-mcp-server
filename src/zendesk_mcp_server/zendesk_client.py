from typing import Dict, Any, List
import json
import urllib.request
import urllib.parse
import base64

from zenpy import Zenpy
from zenpy.lib.api_objects import Comment
from zenpy.lib.api_objects import Ticket as ZenpyTicket


class ZendeskClient:
    def __init__(self, subdomain: str, email: str, token: str):
        """
        Initialize the Zendesk client using zenpy lib and direct API.
        """
        self.client = Zenpy(
            subdomain=subdomain,
            email=email,
            token=token
        )

        # For direct API calls
        self.subdomain = subdomain
        self.email = email
        self.token = token
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        # Create basic auth header
        credentials = f"{email}/token:{token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode('ascii')
        self.auth_header = f"Basic {encoded_credentials}"

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        """
        Query a ticket by its ID
        """
        try:
            ticket = self.client.tickets(id=ticket_id)
            return {
                'id': ticket.id,
                'subject': ticket.subject,
                'description': ticket.description,
                'status': ticket.status,
                'priority': ticket.priority,
                'created_at': str(ticket.created_at),
                'updated_at': str(ticket.updated_at),
                'requester_id': ticket.requester_id,
                'assignee_id': ticket.assignee_id,
                'organization_id': ticket.organization_id
            }
        except Exception as e:
            raise Exception(f"Failed to get ticket {ticket_id}: {str(e)}")

    def get_ticket_comments(self, ticket_id: int) -> List[Dict[str, Any]]:
        """
        Get all comments for a specific ticket.
        """
        try:
            comments = self.client.tickets.comments(ticket=ticket_id)
            return [{
                'id': comment.id,
                'author_id': comment.author_id,
                'body': comment.body,
                'html_body': comment.html_body,
                'public': comment.public,
                'created_at': str(comment.created_at)
            } for comment in comments]
        except Exception as e:
            raise Exception(f"Failed to get comments for ticket {ticket_id}: {str(e)}")

    def post_comment(self, ticket_id: int, comment: str, public: bool = True) -> str:
        """
        Post a comment to an existing ticket.
        """
        try:
            ticket = self.client.tickets(id=ticket_id)
            ticket.comment = Comment(
                html_body=comment,
                public=public
            )
            self.client.tickets.update(ticket)
            return comment
        except Exception as e:
            raise Exception(f"Failed to post comment on ticket {ticket_id}: {str(e)}")

    def get_tickets(self, page: int = 1, per_page: int = 25, sort_by: str = 'created_at', sort_order: str = 'desc') -> Dict[str, Any]:
        """
        Get the latest tickets with proper pagination support using direct API calls.

        Args:
            page: Page number (1-based)
            per_page: Number of tickets per page (max 100)
            sort_by: Field to sort by (created_at, updated_at, priority, status)
            sort_order: Sort order (asc or desc)

        Returns:
            Dict containing tickets and pagination info
        """
        try:
            # Cap at reasonable limit
            per_page = min(per_page, 100)

            # Build URL with parameters for offset pagination
            params = {
                'page': str(page),
                'per_page': str(per_page),
                'sort_by': sort_by,
                'sort_order': sort_order
            }
            query_string = urllib.parse.urlencode(params)
            url = f"{self.base_url}/tickets.json?{query_string}"

            # Create request with auth header
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            # Make the API request
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

            tickets_data = data.get('tickets', [])

            # Process tickets to return only essential fields
            ticket_list = []
            for ticket in tickets_data:
                ticket_list.append({
                    'id': ticket.get('id'),
                    'subject': ticket.get('subject'),
                    'status': ticket.get('status'),
                    'priority': ticket.get('priority'),
                    'description': ticket.get('description'),
                    'created_at': ticket.get('created_at'),
                    'updated_at': ticket.get('updated_at'),
                    'requester_id': ticket.get('requester_id'),
                    'assignee_id': ticket.get('assignee_id')
                })

            return {
                'tickets': ticket_list,
                'page': page,
                'per_page': per_page,
                'count': len(ticket_list),
                'sort_by': sort_by,
                'sort_order': sort_order,
                'has_more': data.get('next_page') is not None,
                'next_page': page + 1 if data.get('next_page') else None,
                'previous_page': page - 1 if data.get('previous_page') and page > 1 else None
            }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            raise Exception(f"Failed to get latest tickets: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to get latest tickets: {str(e)}")

    def get_all_articles(self) -> Dict[str, Any]:
        """
        Fetch help center articles as knowledge base.
        Returns a Dict of section -> [article].
        """
        try:
            # Get all sections
            sections = self.client.help_center.sections()

            # Get articles for each section
            kb = {}
            for section in sections:
                articles = self.client.help_center.sections.articles(section.id)
                kb[section.name] = {
                    'section_id': section.id,
                    'description': section.description,
                    'articles': [{
                        'id': article.id,
                        'title': article.title,
                        'body': article.body,
                        'updated_at': str(article.updated_at),
                        'url': article.html_url
                    } for article in articles]
                }

            return kb
        except Exception as e:
            raise Exception(f"Failed to fetch knowledge base: {str(e)}")

    def create_ticket(
        self,
        subject: str,
        description: str,
        requester_id: int | None = None,
        assignee_id: int | None = None,
        priority: str | None = None,
        type: str | None = None,
        tags: List[str] | None = None,
        custom_fields: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """
        Create a new Zendesk ticket using Zenpy and return essential fields.

        Args:
            subject: Ticket subject
            description: Ticket description (plain text). Will also be used as initial comment.
            requester_id: Optional requester user ID
            assignee_id: Optional assignee user ID
            priority: Optional priority (low, normal, high, urgent)
            type: Optional ticket type (problem, incident, question, task)
            tags: Optional list of tags
            custom_fields: Optional list of dicts: {id: int, value: Any}
        """
        try:
            ticket = ZenpyTicket(
                subject=subject,
                description=description,
                requester_id=requester_id,
                assignee_id=assignee_id,
                priority=priority,
                type=type,
                tags=tags,
                custom_fields=custom_fields,
            )
            created_audit = self.client.tickets.create(ticket)
            # Fetch created ticket id from audit
            created_ticket_id = getattr(getattr(created_audit, 'ticket', None), 'id', None)
            if created_ticket_id is None:
                # Fallback: try to read id from audit events
                created_ticket_id = getattr(created_audit, 'id', None)

            # Fetch full ticket to return consistent data
            created = self.client.tickets(id=created_ticket_id) if created_ticket_id else None

            return {
                'id': getattr(created, 'id', created_ticket_id),
                'subject': getattr(created, 'subject', subject),
                'description': getattr(created, 'description', description),
                'status': getattr(created, 'status', 'new'),
                'priority': getattr(created, 'priority', priority),
                'type': getattr(created, 'type', type),
                'created_at': str(getattr(created, 'created_at', '')),
                'updated_at': str(getattr(created, 'updated_at', '')),
                'requester_id': getattr(created, 'requester_id', requester_id),
                'assignee_id': getattr(created, 'assignee_id', assignee_id),
                'organization_id': getattr(created, 'organization_id', None),
                'tags': list(getattr(created, 'tags', tags or []) or []),
            }
        except Exception as e:
            raise Exception(f"Failed to create ticket: {str(e)}")

    def update_ticket(self, ticket_id: int, **fields: Any) -> Dict[str, Any]:
        """
        Update a Zendesk ticket with provided fields using Zenpy.

        Supported fields include common ticket attributes like:
        subject, status, priority, type, assignee_id, requester_id,
        tags (list[str]), custom_fields (list[dict]), due_at, etc.
        """
        try:
            # Load the ticket, mutate fields directly, and update
            ticket = self.client.tickets(id=ticket_id)
            for key, value in fields.items():
                if value is None:
                    continue
                setattr(ticket, key, value)

            # This call returns a TicketAudit (not a Ticket). Don't read attrs from it.
            self.client.tickets.update(ticket)

            # Fetch the fresh ticket to return consistent data
            refreshed = self.client.tickets(id=ticket_id)

            return {
                'id': refreshed.id,
                'subject': refreshed.subject,
                'description': refreshed.description,
                'status': refreshed.status,
                'priority': refreshed.priority,
                'type': getattr(refreshed, 'type', None),
                'created_at': str(refreshed.created_at),
                'updated_at': str(refreshed.updated_at),
                'requester_id': refreshed.requester_id,
                'assignee_id': refreshed.assignee_id,
                'organization_id': refreshed.organization_id,
                'tags': list(getattr(refreshed, 'tags', []) or []),
            }
        except Exception as e:
            raise Exception(f"Failed to update ticket {ticket_id}: {str(e)}")

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        Get a user by their ID.

        Args:
            user_id: The ID of the user to retrieve

        Returns:
            Dict containing user information
        """
        try:
            user = self.client.users(id=user_id)
            return {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'phone': getattr(user, 'phone', None),
                'organization_id': user.organization_id,
                'created_at': str(user.created_at),
                'updated_at': str(user.updated_at),
                'time_zone': getattr(user, 'time_zone', None),
                'locale': getattr(user, 'locale', None),
                'active': getattr(user, 'active', None),
                'verified': getattr(user, 'verified', None),
                'tags': list(getattr(user, 'tags', []) or []),
            }
        except Exception as e:
            raise Exception(f"Failed to get user {user_id}: {str(e)}")

    def search_users_by_email(self, email: str) -> List[Dict[str, Any]]:
        """
        Search for users by email address.

        Args:
            email: Email address to search for (can be partial)

        Returns:
            List of users matching the email
        """
        try:
            users = self.client.search(type='user', email=email)
            return [{
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'organization_id': user.organization_id,
                'created_at': str(user.created_at),
                'active': getattr(user, 'active', None),
            } for user in users]
        except Exception as e:
            raise Exception(f"Failed to search users by email '{email}': {str(e)}")

    def create_user(self, email: str, name: str, **kwargs) -> Dict[str, Any]:
        """
        Create a new Zendesk user.

        Args:
            email: User's email address
            name: User's full name
            **kwargs: Optional fields like role, phone, organization_id, etc.

        Returns:
            Dict containing created user information
        """
        try:
            from zenpy.lib.api_objects import User

            user = User(
                email=email,
                name=name,
                role=kwargs.get('role', 'end-user'),
                phone=kwargs.get('phone'),
                organization_id=kwargs.get('organization_id'),
                time_zone=kwargs.get('time_zone'),
                locale=kwargs.get('locale'),
            )

            created = self.client.users.create(user)

            return {
                'id': created.id,
                'name': created.name,
                'email': created.email,
                'role': created.role,
                'organization_id': created.organization_id,
                'created_at': str(created.created_at),
                'active': getattr(created, 'active', None),
            }
        except Exception as e:
            raise Exception(f"Failed to create user: {str(e)}")

    def get_user_tickets(self, user_id: int, status: str = None) -> List[Dict[str, Any]]:
        """
        Get all tickets requested by a specific user.

        Args:
            user_id: The ID of the user
            status: Optional status filter (new, open, pending, solved, closed)

        Returns:
            List of tickets requested by the user
        """
        try:
            # Use the search API to find tickets by requester
            search_query = f'type:ticket requester:{user_id}'
            if status:
                search_query += f' status:{status}'

            tickets = self.client.search(query=search_query, type='ticket')

            ticket_list = []
            for ticket in tickets:
                ticket_list.append({
                    'id': ticket.id,
                    'subject': ticket.subject,
                    'description': ticket.description,
                    'status': ticket.status,
                    'priority': ticket.priority,
                    'created_at': str(ticket.created_at),
                    'updated_at': str(ticket.updated_at),
                    'requester_id': ticket.requester_id,
                    'assignee_id': ticket.assignee_id,
                })

            return ticket_list
        except Exception as e:
            raise Exception(f"Failed to get tickets for user {user_id}: {str(e)}")

    def list_macros(self, access: str = None, active: bool = None, category: int = None) -> List[Dict[str, Any]]:
        """
        List all macros accessible to the current user.

        Args:
            access: Optional filter by access level (personal, agents, shared, account)
            active: Optional filter by active status (true/false)
            category: Optional filter by category ID

        Returns:
            List of macros with their details
        """
        try:
            # Build query parameters
            params = {}
            if access:
                params['access'] = access
            if active is not None:
                params['active'] = str(active).lower()
            if category:
                params['category'] = str(category)

            query_string = urllib.parse.urlencode(params) if params else ''
            url = f"{self.base_url}/macros.json"
            if query_string:
                url += f"?{query_string}"

            # Create request with auth header
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            # Make the API request
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

            macros_data = data.get('macros', [])

            # Process macros to return essential fields
            macro_list = []
            for macro in macros_data:
                macro_list.append({
                    'id': macro.get('id'),
                    'title': macro.get('title'),
                    'description': macro.get('description'),
                    'active': macro.get('active'),
                    'actions': macro.get('actions', []),
                    'restriction': macro.get('restriction'),
                    'created_at': macro.get('created_at'),
                    'updated_at': macro.get('updated_at'),
                })

            return macro_list
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            raise Exception(f"Failed to list macros: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to list macros: {str(e)}")

    def get_macro(self, macro_id: int) -> Dict[str, Any]:
        """
        Get a specific macro by its ID.

        Args:
            macro_id: The ID of the macro to retrieve

        Returns:
            Dict containing macro details including actions
        """
        try:
            url = f"{self.base_url}/macros/{macro_id}.json"

            # Create request with auth header
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            # Make the API request
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

            macro = data.get('macro', {})

            return {
                'id': macro.get('id'),
                'title': macro.get('title'),
                'description': macro.get('description'),
                'active': macro.get('active'),
                'actions': macro.get('actions', []),
                'restriction': macro.get('restriction'),
                'created_at': macro.get('created_at'),
                'updated_at': macro.get('updated_at'),
            }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            raise Exception(f"Failed to get macro {macro_id}: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to get macro {macro_id}: {str(e)}")

    def apply_macro_to_ticket(self, ticket_id: int, macro_id: int) -> Dict[str, Any]:
        """
        Preview what changes a macro would make to a ticket.
        This does NOT actually apply the macro - it returns the changes that would be made.
        Use update_ticket() with the returned fields to actually apply the changes.

        Args:
            ticket_id: The ID of the ticket
            macro_id: The ID of the macro to apply

        Returns:
            Dict containing the ticket with proposed changes from the macro
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}/macros/{macro_id}/apply.json"

            # Create request with auth header
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            # Make the API request
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

            result = data.get('result', {})
            ticket_changes = result.get('ticket', {})
            comment = result.get('comment', {})

            return {
                'ticket_changes': {
                    'subject': ticket_changes.get('subject'),
                    'status': ticket_changes.get('status'),
                    'priority': ticket_changes.get('priority'),
                    'type': ticket_changes.get('type'),
                    'assignee_id': ticket_changes.get('assignee_id'),
                    'group_id': ticket_changes.get('group_id'),
                    'tags': ticket_changes.get('tags'),
                    'custom_fields': ticket_changes.get('custom_fields'),
                },
                'comment': {
                    'body': comment.get('body'),
                    'html_body': comment.get('html_body'),
                    'public': comment.get('public'),
                } if comment else None,
                'macro_id': macro_id,
                'ticket_id': ticket_id,
            }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            raise Exception(f"Failed to apply macro {macro_id} to ticket {ticket_id}: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to apply macro {macro_id} to ticket {ticket_id}: {str(e)}")