/**
 * The market API and UI deliberately cap one page at 20 rows. Both responsive
 * table representations are mounted, so reassess virtualization before this
 * cap is raised above 100 rows.
 */
export const MARKET_PAGE_SIZE = 20
export const MARKET_VIRTUALIZATION_REVIEW_THRESHOLD = 100
