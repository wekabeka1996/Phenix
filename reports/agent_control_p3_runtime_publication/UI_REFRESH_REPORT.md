# UI refresh report

Cockpit production `/economics` returned HTTP 200 with the SPA shell. Ten backing API refreshes produced ten distinct packet ids with fresh runtime-publication market and feature data. Cockpit remained disarmed and `AGENT_FEED_ACTIONS_ENABLED=false` remains test-covered.

Rendered DOM refresh is not observed. The required in-app browser backend was unavailable (`available browsers=[]`), and no unrelated backend was substituted. Server/API data movement and component/build smoke are proven; pixels are not.
