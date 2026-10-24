"use strict";

function setupHistoryFilter(filterId, tableId, countId, emptyId) {
    const filter = document.getElementById(filterId);
    const table = document.getElementById(tableId);
    const count = document.getElementById(countId);
    const empty = document.getElementById(emptyId);

    if (!filter) {
        return;
    }

    function applyFilter() {
        const rows = table
            ? Array.from(table.querySelectorAll("tbody tr"))
            : [];
        const selectedStatus = filter.value;
        let visibleCount = 0;

        rows.forEach((row) => {
            const matches =
                selectedStatus === "all" ||
                row.dataset.status === selectedStatus;

            row.hidden = !matches;
            if (matches) {
                visibleCount += 1;
            }
        });

        if (count) {
            count.textContent = `${visibleCount} of ${rows.length} shown`;
        }

        if (empty) {
            empty.hidden = rows.length === 0 || visibleCount !== 0;
        }
    }

    filter.addEventListener("change", applyFilter);
    applyFilter();
}

setupHistoryFilter(
    "connectionStatusFilter",
    "connectionHistoryTable",
    "connectionFilterCount",
    "connectionNoMatches",
);

setupHistoryFilter(
    "executionStatusFilter",
    "executionHistoryTable",
    "executionFilterCount",
    "executionNoMatches",
);
