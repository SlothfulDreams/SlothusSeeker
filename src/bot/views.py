"""Reusable Discord UI views."""

import math

import discord

from src.bot.embeds import create_company_list_embed
from src.config.settings import COMPANIES_PER_PAGE


class CompanyListView(discord.ui.View):
    """Button pagination for the company allow-list."""

    def __init__(
        self,
        companies: list[dict],
        owner_id: int,
        per_page: int = COMPANIES_PER_PAGE,
    ):
        super().__init__(timeout=180)
        self.companies = companies
        self.owner_id = owner_id
        self.per_page = max(1, per_page)
        self.page = 0
        self.total_pages = max(1, math.ceil(len(companies) / self.per_page))
        self._sync_button_state()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "Only the user who ran `/companies list` can page this list.",
            ephemeral=True,
        )
        return False

    def embed(self) -> discord.Embed:
        """Return the embed for the current page."""
        return create_company_list_embed(
            self.companies,
            page=self.page,
            per_page=self.per_page,
        )

    def _sync_button_state(self) -> None:
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ):
        self.page = max(0, self.page - 1)
        self._sync_button_state()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_page(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._sync_button_state()
        await interaction.response.edit_message(embed=self.embed(), view=self)
