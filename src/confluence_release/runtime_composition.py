"""Add Confluence to a host's existing Pressroom services without an AIL import.

The running host owns its manuscript gateway, approval/read adapters, OAuth and
transport. Pass those objects here; this function neither reconstructs them nor
mutates a running server/registry. Install the returned core in the host factory.
Pass the host's existing writer_profiles service too, just like responses and
system. None is only for hosts where that feature is not configured.
"""
from __future__ import annotations
from .adapter import HereNowDestinationAdapter


def create_pressroom_core(session_factory, *, config, manuscripts, approvals,
                          existing_destinations=(), responses=None,
                          editorial_state=None, system=None, writer_profiles=None):
    from pressroom.services import PressroomToolCore, PublicationWorkflow
    if any(d.key == 'confluence' for d in existing_destinations):
        raise ValueError('Confluence destination is already composed')
    destination = HereNowDestinationAdapter(session_factory, config)
    destinations = tuple(existing_destinations) + (destination,)
    return PressroomToolCore(manuscripts, destinations,
        publication_workflow=PublicationWorkflow(session_factory, destinations),
        approvals=approvals, responses=responses, editorial_state=editorial_state,
        system=system, writer_profiles=writer_profiles)
