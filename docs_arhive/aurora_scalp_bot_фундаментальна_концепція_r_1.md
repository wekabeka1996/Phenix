# Aurora+Scalp Bot                                                     R1

>               : **          ,                     .**                                ,                                                                                    .                                                                               ,                           . **                                  90%**, **XAI                                             **                               .

---

## 1)                           

**        .**                      24/7                                        :
- **Aurora (Research+Orchestrator)**                                    ,                                    L2/L3,                              ,                                        ,                                            (EVT   CVaR),            **                               **                                                   .
- **Scalp Bot (Execution)**                                                   shadow/paper/live    maker/taker               , TCA      fill                         .

**              .**                 **                /                                               **                                                 .                                  : **SOL                (        . SOON)**                                                . BTC/ETH                                             ,                                                             .

**                       .** **                    ,                                     **: Aurora                                                    **                    **                                                                  ,                        ,                       ,                                              DD.              **                                                       TCA**                                       CVaR.

---

## 2)                  (              )
1. **Edge            TCA.**                                                                   **          ** fees,                 , adverse selection,                                             .
2. **                                             .**                         p                                ECE/Brier/LogLoss                                    (ICP/                  ).
3. **                                      .**                                       **CVaR95** (          /          /                )    EVT                                .
4. **                               .**                                                                         ,                                                 (TCA).                                                 ,          **                                 **.
5. **                                               .**                                                                   **SPRT/GLR**            baseline    shadow                          .
6. **                       .**                                                                (                                                         ).
7. **XAI                 .**                                               : features   score   p   E[  ]   risk   gates   WHY           ,                                                  edge   breakdown.
8. **                       hard   code.**                                  SSOT                   ;                                               .

---

## 3)               
-         :                             \(t \in \mathbb{N}\) (event   time),            \(\Delta t\)                  .
-         /          : \(P_{bid}(t), P_{ask}(t)\),            \(\mathrm{spr}(t)=P_{ask}-P_{bid}\).
-                                                  : \(V_{bid}, V_{ask}\);                     Lk: \(\sum_{\ell\le k}V^{(\ell)}\).
-          (            ): \(x_t \in \mathbb{R}^d\);         : \(S_t\);                                        : \(p_t\in(0,1)\).
-                                :             /             \(G, L\) (             /    ),                \(c\) (fees+slippage+latency     rebates).
-                                         : \(E[\Pi]\);                                     \(\boldsymbol{\mu},\ \Sigma\).
-                          : \(f\in[0,f_{\max}]\);                              : \(\lambda_{cal},\lambda_{reg},\lambda_{liq},\lambda_{dd},\lambda_{lat}\).

---

## 4) Edge                                                      

### 4.1.                                                     
\[
E[\Pi] \,=\, p\,G\; -\; (1-p)\,L\; -\; c.
\]
                           ,          \(E[\Pi]>0\) **           TCA                   **.                                         payoff   ratio \(r=G/L\)                                      \(c'=c/L\):
\[
E[\Pi]>0 \iff p > p^*(c') \,=\, \frac{1+c'}{1+r}.
\]
                :                                           \(\delta\ge 0.01\): \(p>p^*(c')+\delta\).

### 4.2.                                        edge vs Sharpe
           \(m\)                      PnL/          , \(s\)           /          , \(N\)             /        .                       Sharpe:
\[
SR_d=\frac{\sqrt{N}\,m}{s}, \qquad SR_{\text{      }}\approx SR_d\sqrt{21}.
\]
         \(SR_{\text{      }}\ge2\Rightarrow SR_d\ge 2/\sqrt{21}\).                                                                             \(m\)                            **           TCA**                                               .

### 4.3. Edge   Budget (                                 )
\[
E[\Pi] = \underbrace{E[\Pi]_{raw}}_{\text{          }}\; -\; \underbrace{c_{fees}}_{\text{              }}\; -\; \underbrace{c_{slip, in/out}}_{\text{                }}\; -\; \underbrace{c_{adv}}_{\text{adverse sel.}}\; -\; \underbrace{c_{lat}}_{\text{                      }}\; +\; \underbrace{r_{reb}}_{\text{              }}.
\]
                                                                                      (                         ).

---

## 5)                                                          

### 5.1.                      
- **OBI (Order Book Imbalance)**      best        Lk:
\[
\mathrm{OBI} = \frac{V_{bid}-V_{ask}}{V_{bid}+V_{ask}}.
\]
- **                       **            best   volumes:
\[
P_{\mathrm{micro}}=\frac{V_{ask}\,P_{bid}+V_{bid}\,P_{ask}}{V_{bid}+V_{ask}},\quad \Delta P_{\mathrm{micro}}=P_{\mathrm{micro}}(t)-P_{\mathrm{micro}}(t-\Delta t).
\]
- **TFI (Trade Flow Imbalance)**                                            \(W\):
\[
\mathrm{TFI} = \frac{\sum_{\tau\in W}\mathrm{sign}(\text{trade}\_\tau)\cdot \mathrm{size}_\tau}{\sum_{\tau\in W}\mathrm{size}_\tau}.
\]
- **Absorption.**                                                                                :                                                                                                                      \(W\).

### 5.2.                                               
                                            (MAD/Huber).                        **half   life           **                                                                                     ,                                          (                                       ).

### 5.3. Universe             
                                 :                        L5,           /    ,                               (bps),                                    ,                                                   .                    \(K\)                   ;                                                   .

---

## 6)                                   (Score     Probability)

### 6.1.                                                                                               
\[
S_i(t) = w^\top x_i(t) \; + \; \gamma\,\beta_{i|\mathrm{SOL}}(t)\, r_{\mathrm{SOL}}(t-\tau^*(t)).
\]
       \(r_{\mathrm{SOL}}\)                                 SOL                 LOB           ; \(\beta_{i|\mathrm{SOL}}\)                                          i      SOL; \(\tau^*\)                                         (      .   7).

### 6.2.                                         
\[
\tilde p_i(t) = \sigma\big(a + b\,S_i(t)\big),\qquad p_i(t)=\mathrm{Calibrate}\big(\tilde p_i(t)\big),
\]
     **Calibrate**     Platt/Isotonic                             ECE/Brier/LogLoss    ICP                 .

### 6.3. ICP/                                  
                                                /           p   values;                                                        **                                ** (coverage/efficiency                          ).

---

## 7)                                             (                   )

### 7.1.                          
             \(\beta_{i|\mathrm{SOL}}\)                                  (                                 /GLM):
\[
r_i(t) = \alpha + \beta_{i|\mathrm{SOL}}\, r_{\mathrm{SOL}}(t) + \varepsilon_t,\quad \beta\text{                            }.
\]
### 7.2.        \(\tau^*\)
               \(\tau\)                                                          (                             /GLR/transfer entropy):
\[
\tau^*(t) = \arg\max_{\tau\in\mathcal{T}}\; \mathrm{Predictability}\big(r_{\mathrm{SOL}}(t-\tau)\to r_i(t)\big).
\]
                         \(\tau^*\)                             ,                                                    (SPRT                                          ).

---

## 8)                              

### 8.1. Page   Hinkley / GLR
                                                  /                                /                          :
\[
PH_t = PH_{t-1} + (x_t - \mu_0 - \delta)\quad \text{                         } PH_t<\min_{s\le t}PH_s;\ \text{                    } PH_t-\min PH > h.
\]
GLR                                                                                           /            .

### 8.2. HMM (                   )
                                              /          /          ;                                     /                       \(\lambda_{reg}\)                                            .

---

## 9) TCA    Fill Simulator

### 9.1.                                
- **Maker:**           ,                         ,                                       **trade   to   book ratio (TBR)**; hazard               :
\[
\Pr(\text{fill by }t) = 1 - \exp\Big(-\int_0^t \lambda_{\text{fill}}(u)\,du\Big),\quad \lambda_{\text{fill}} = f(\text{TBR},\ \text{queue pos},\ \mathrm{spr}).
\]
- **Taker:**                                                  ,                           ,                                           .

### 9.2.                           adverse selection
                                                                                         \(\ell\):
\[
E[\Pi(\ell)] \approx E[\Pi(0)] - \kappa\,\ell,\quad \kappa\,\text{(    /    )    live   shadow}.
\]
SLA           :                   ,          \(E[\Pi(\ell)]>0\)                  ; \(\ell\le E[\Pi(0)]/\kappa\).

### 9.3. Edge   Budget Dashboard
                                  (      .   4.3)                                                                                   .

---

## 10)                           (Entry Rules)

1. **           p:** \(p_i(t) > p^*_i(c'_i)+\delta\),      \(p^*_i(c')=\tfrac{1+c'}{1+r}\), \(r=G/L\), \(c'=c/L\).
2. **                         :**          \(\in\)                        (Page   Hinkley/GLR/HMM).
3. **TCA           :**                                   \(E[\Pi(\ell)]>0\)                           SLA.
4. **Risk             :**                        ,                           /                                    ; **CVaR95**                            ;                 /                                             .
5. **                  /                :**                                           ,                                                   **SPRT/GLR**            baseline.

---

## 11)                              :                                                                       

### 11.1.                                                   i
\[
 f^{raw}_{i} = \mathrm{clip}\!\left(\frac{b_i p_i-(1-p_i)}{b_i},\ 0,\ f_{\max}\right),\quad b_i = \frac{G_i}{L_i}.
\]

### 11.2.                                   (                                 )
\[
\boldsymbol{f}^{port} = \rho\,\Sigma^{-1}\,\boldsymbol{\mu},\quad \text{     }\boldsymbol{\mu}=\{E[\Pi_i]\},\ \Sigma=\mathrm{Cov}(\text{PnL/          }).
\]
\(\rho\)                          ,        \(\mathrm{CVaR}^{port}_{95}\le \tau\) (                                                    ).

### 11.3.                                                         
\[
 M = \lambda_{cal}\cdot\lambda_{reg}\cdot\lambda_{liq}\cdot\lambda_{dd}\cdot\lambda_{lat},\qquad f_i = \mathrm{clip}\big(M\cdot f^{comb}_i, 0, f_{\max}\big).
\]
- \(\lambda_{cal}\)                                           (ECE/LogLoss),                                     ;  
- \(\lambda_{reg}\)                              ;  
- \(\lambda_{liq}\)                           /          ;  
- \(\lambda_{dd}\)                                       drawdown;  
- \(\lambda_{lat}\)                                             SLA.

### 11.4.                       
- **Fractional   Kelly:**              0.3   0.6  ,                         \(\uparrow\)      1.0                                     .  
- **Shrinkage p:**                                             : \(p\leftarrow \lambda p + (1-\lambda)\cdot 0.5\).  
- **CVaR           :**                                                                  .

---

## 12)                            (EVT   CVaR)

### 12.1. CVaR95
\[
\mathrm{CVaR}_{95}(\Pi) = E\big[\Pi\mid \Pi\le q_{0.05}\big],\quad q_{0.05}=\text{VaR}_{95}.
\]

### 12.2. POT/GPD                                         
           \(u\),                  \(Y=\Pi-u\mid \Pi\le u\).                    GPD (\(\xi,\beta\))                  MLE/                                             CI;                                .                             \(\mathrm{CVaR}_{95}\)                /                              .

---

## 13)                         ,                                       

### 13.1.                         
- **Platt/Isotonic**                                         .               : **ECE     0.05**, **Brier     0.17**, **LogLoss**                               .  
- **Reliability             **                                           100%              (                              ).

### 13.2.           
- **CUSUM/Page   Hinkley/GLR**                                               ;                                            \(\lambda_{cal}\)   /       fractional   Kelly.  
- **PIT                   **                                                 .

### 13.3. SPRT/GLR    Governance
                                   vs baseline    shadow:
\[
\Lambda_t=\sum_{i\le t}\log\frac{f(x_i\mid H_1)}{f(x_i\mid H_0)},\quad \text{                      } \Lambda_t>\log A \text{      } <\log B.
\]
             \(A=(1-\beta)/\alpha\), \(B=\beta/(1-\alpha)\),         . \(\alpha=0.05,\ \beta=0.2\).                                                                                      **                     net   expectancy            TCA**.

---

## 14)                    (Execution)    SLA

### 14.1. Maker vs Taker
                                           **c**      4.3                       \(E[\Pi]_{raw}\)                     \(\ell\). Maker                                    hazard                     ; Taker                                                             adverse selection.

### 14.2.                                                                        
            /                                                                    partial fills                                                                                              (                                          ).

### 14.3. SLA                       
                                                       ; deny,                                    \(E[\Pi(\ell)]\)                                       .

---

## 15) XAI                                                             
     **                         **                     :
-          (                               ),         /        /\(\tilde p\)/\(p\) +                                              ;
- **edge   breakdown** (      .   4.3);
-           : spread/vol/latency/CVaR/inventory + WHY                          /              ;
-           /                      /                   /                             ;
-                                   (Sharpe, ECE/Brier/LogLoss, CVaR CI).

            : no   trades   too   long, spike   denies, latency spikes, calibration   drift, CVaR breach.

---

## 16) High   level Architecture Diagram                                

**                                            (                                       ):**
1. **Market Data Ingestion (L2/L3, Trades)**                         ,                                      ,            look   ahead.  
2. **Feature Builder**     OBI/TFI/  P_micro/Absorption, SOL   referenced             , robust scaling.  
3. **Signal Engine**     \(S_i(t)=w^\top x_i + \gamma\,\beta_{i|SOL}\,r_{SOL}(t-\tau^*)\).  
4. **Calibrator + ICP**     \(\tilde p\to p\), reliability/ECE/LogLoss.  
5. **Regime Detector (PH/GLR/HMM)**     \(\lambda_{reg}\)        allow                        .  
6. **TCA + Fill Simulator**                  \(c\), \(E[\Pi(\ell)]\), SLA                     .  
7. **Risk Engine (EVT   CVaR)**     per   trade/          /                                 , **CVaR             **.  
8. **Aurora Kelly Orchestrator**     \(f^{raw}\), \(\boldsymbol{f}^{port}=\rho\Sigma^{-1}\boldsymbol{\mu}\),                \(M\);                  \(f_i\).  
9. **Execution Layer (Scalp Bot)**     maker/taker               ,                       , SLA                       ,                                    .  
10. **Exchange**                               /              /              .  
11. **XAI/Observability**                              , edge   dashboard,             .  
12. **Knowledge Base**                              ,                                    ,                                                     /      .  
13. **Governance + SPRT/GLR**               /rollback                                             ;                                                              live.

**                                :**
-                        TCA                                                             /\(\kappa\).  
-             /                             \(\lambda_{cal},\lambda_{reg}\)                                    .  
- Knowledge Base                                   universe                                  .

---

## 17)                             (Exit)                                        
- **TP/Trail/Breakeven**                     \(p, r, \mathrm{spr}, \ell\)      **SPRT**                                   /                                                                      .  
-                                                **CVaR               **                                 .  
-                                           edge   breakdown     /          .

---

## 18)                               (               )
- **           TCA:** \(E[\Pi]>0\)                                                      ;                                                                 raw   edge.  
- **                        :** ECE     0.05, Brier     0.17, LogLoss                               ; reliability                                                        .  
- **          :** \(\mathrm{CVaR}_{95}\) per   trade/                                        CI; EVT                                                   .  
- **Perf:** SLA                                        ; \(\kappa\)                                              .  
- **                    :** SR_{      }     2 (Newey   West),                        expectancy                                                      SOON/        2             .  
- **SPRT/GLR:**                        ,                            live,                                                            .

---

## 19)               ,                             ,                          (              )
- **Windows Service/Docker**        24/7;                                                   ; rollback.  
- **            :** no   trades, spike   denies, latency/CVaR/calibration drift;                          ;                                              .  
- **SSOT                 **                                                    ;          hard   code.  
- **                                           :**                                                                                                                          .

---

###                     
Aurora+Scalp Bot                        ,      **                                                                                                                           (SOL             )**,                                 **                                             **,                    **                    TCA             **,                            **                               **        **EVT   CVaR**    **SLA                       **,                                                       **XAI                       **    **                                                   **.                                                                                                                                                       :               ,           ,               ,                                                                 .



---

## R1.2                   :                                           Grok 4 (                  )

### A) Live Regime   Stratified OOS   board
                                        : {trend, grind, chaos}.                                                                                        TCA:   E[Pi]^R (                        ), SR^R (Sharpe    HAC/Newey   West), ECE^R, Brier^R, LogLoss^R.                   :   E[Pi]^R > 0      SR^R                                                                                                 ;                                                 .

### B)                                            shrinkage (Ledoit   Wolf)
                                                        : Sigma_hat =    * F + (1       ) * S,      S                                             PnL/          , F     diag(S)             * I,        [0,1]                                 Ledoit   Wolf.           3                                   tail                                   tail   copula / co   CVaR                       CVaR                         .

### C) Prequential (                  )                                       
                                                                                                      : M_t = (1     ) * M_{t   1} +    * m_t,      M     {ECE, Brier, LogLoss}.      residual logit                CUSUM/GLR;                         shrink p        p + (1     )*0.5                           _cal.

### D) Alpha   spending / FDR    Governance
             ledger                                                              (                  Pocock/OBF)                               FDR                      Benjamini   Hochberg                                             /            .               :                          live                     ID                         ,                                        .

### E)                                           (Hayashi   Yoshida)
                                         /                                                           HY;          *     GLR                    SPRT                                 purged CV + embargo.                                        FDR                   ;                                                                                                 .

### F) Fill   hazard      Cox + Hawkes
                                                (maker):   _fill(t|Z) =   0(t) * exp(  ^T Z),      Z = {TBR,                             ,           , OBI, cancel rate}. Order   flow                    Hawkes                                                  (adverse   bursts). Acceptance: MAE          fill     X     ; Brier(P(fill))     0.18; 3                                                                taker                         p*(c').

### G)                                                                  
  _cal = exp(     _cal * ECE_t) * exp(     _cal * LogLoss_t);
  _dd = (1 + DD_t/  )^(     );
  _lat = max{0, 1        * (latency)/E};
  _liq = min{1, Q_depth_Lk / Q_target}.

### H)                         CVaR                        (Rockafellar   Uryasev)
                      w*                                              L2/L3   replay                                                       RU        CVaR (   = 0.95).                                     :        E[f*]                               (p,r),                               f* (20                          ).                  1/2   Kelly.

### I)                      SLO/SLA                          
SLA                          ,             , circuit   breakers (                         /             L5).                                                   Core   Lane (taker   only,                                ). Chaos                                 .

### J) Acceptance                      (                    )
    Regime   OOS:   E[Pi]^R > 0, SR               HAC                     ,                             CVaR.
    LW                       :                                                 f_i      co   CVaR                                   .
    Prequential:                                ECE/Brier/LogLoss                  ;                            M.
    Governance: alpha   ledger                          ; FDR                                           .

                :                                         Two   Lane + Complexity Budget  :                                                    live                                       , SPRT/GLR                                        .

