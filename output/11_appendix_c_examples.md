# Appendix C: Illustrative Examples by Method

*Auto-extracted from the corpus to illustrate how each method 
captures different dimensions of coverage bias.*


## 1. Prosecutor-Attributed Theme Detection (d = 0.42)

This method detects anti-prosecutor narrative themes (recall campaigns, 
soft-on-crime framing, etc.) attributed to specific prosecutors.


### Example 1a: High theme score (Progressive prosecutor)

**Headline**: Boudin might be in trouble if poll holds
**Date**: 2022-03-16
**Publication**: San Francisco Chronicle
**Prosecutor**: Chesa Boudin (Progressive)
**Score (ta_composite_score)**: 17.5000
**Details**: crime_rising, case_dismissal, recall (4 detection methods)

> boudin might be in trouble if poll holds san francisco district attorney chesa boudin has just 12 weeks left to make perhaps the biggest case of his career: convincing the city's frustrated voters that he should keep his job. but a new poll, commissioned by the campaign seeking to recall boudin, suggests that might be a daunting task. of 800 voters likely to participate in the june 7 election, 68% said they would vote yes on recalling boudin. seventy-four percent said they have an unfavorable opinion of him, and 78% rated his job performance as "only fair" or "poor." the poll, conducted feb. 17-21 via landlines, cell phones, email and texts, has a margin of error of plus or minus 4.4 percentage points, which means the pollsters are 95% confident that support for recalling boudin is no more than 4.4 percentage points off from 68%. it was offered in english and chinese. the polling company did not offer the questions in spanish, saying the monolingual spanish-speaking electorate is estimated to be very small for the june primary. the poll was conducted by emc research, a respected longtime polling company in the bay area that provided questions showing the poll was [...]

### Example 1b: Recall campaign theme (Progressive)

### Example 1c: Soft-on-crime theme (Progressive)

**Headline**: 'Boudin Blunders': SF DA's downfall leading up to recall
**Date**: 2022-06-08
**Publication**: kron4.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (ta_composite_score)**: 17.1900
**Details**: crime_rising, soft_on_crime, case_dismissal, recall, public_safety_failure (4 detection methods)

> 'boudin blunders': sf da's downfall leading up to recall san francisco (kron) -- chesa boudin's tenure as san francisco district attorney was marred by battles with the police department and clashes with prosecutors who viewed him as soft on crime. at the polls on tuesday, san franciscans overwhelmingly voted to oust their progressive district attorney. partial returns showed 60% of voters supported recalling boudin. boudin, 41, is a former public defender. he narrowly won office in november 2019 with a platform promising to seek alternatives to incarceration, end the racist war on drugs, and hold police officers accountable. reducing incarceration rates was a personal issue for boudin. his father served four decades behind prison bars for his role in a 1981 robbery in new york. but over the past two years in san francisco, brazen shoplifting, car break-ins, drug dealing, home burglaries, and attacks against asian american residents left blackeyes on boudin's time in office. boudin's critics say his policies embolden criminals to commit crimes without fear of consequences. a heated recall campaign, "yes on h," ensued. brooke jenkins, one of san francisco's top homicide prosecutors, left the district attorney's office and joined the recall campaign. jenkins said she quit [...]

### Example 1d: No themes detected (Traditional prosecutor)

**Headline**: Newsom, SF leaders to form joint task force to battle fentanyl crisis
**Date**: 2023-10-27
**Publication**: nbcbayarea.com
**Prosecutor**: Brooke Jenkins (Traditional)
**Score (ta_composite_score)**: 0.0000
**Details**: No anti-prosecutor themes detected

> newsom, sf leaders to form joint task force to battle fentanyl crisis gov. gavin newsom and city leaders are upping the ante in the fight against fentanyl in san francisco. newsom, mayor london breed and top law enforcement officials from the city and state announced friday a joint task force to investigate opioid-linked deaths and poisonings in san francisco, according to a release from the governor's office. the new task force will include personnel from the san francisco police department, the san francisco district attorney's office, the california highway patrol and the california national guard. according to the governor's office, the task force will treat opioid deaths in san francisco similar to homicide cases, using standard procedures to document deaths, gather evidence, determine who and where are the suppliers of fentanyl and hold those drug traffickers accountable. "the opioid crisis has claimed too many, and fentanyl traffickers must be held accountable including, as appropriate, for murder," newsom said in a statement. "this task force is fighting for those affected by this crisis -- for victims and loved ones who deserve peace. working together, we will continue providing treatment and resources to help those struggling with substance use -- and secure [...]


## 2. Keyword Bias Score (Method C, d = -0.20)

Weighted keyword scoring based on crime-related terminology, 
negativity markers, and prosecutor-specific framing.


### Example 2a: Most negative keyword score (Progressive)

**Headline**: Boudin's impact on prosecutions
**Date**: 2021-11-07
**Publication**: San Francisco Chronicle
**Prosecutor**: Chesa Boudin (Progressive)
**Score (score_keywords)**: -0.5556
**Details**: Keyword themes: releasing_criminals, case_dismissal, office_dysfunction, recall, public_safety_failure

> boudin's impact on prosecutions when chesa boudin ran for san francisco district attorney in 2019, he promised to approach crime differently than his predecessors, in part by no longer prosecuting lower-level offenses such as recreational drug use. he also pledged to take more rape cases to trial, even if that meant he would lose those cases more frequently. less than two years after taking office, boudin faces a likely recall election after critics of his administration garnered more than 83,000 signatures from residents who believe he has made the city less safe. to explore that claim, the chronicle conducted a comprehensive review of how often his office decides to prosecute arrested individuals and how often it secures convictions in selected types of crime. boudin's overall charging rate is 48%, slightly lower than predecessor george gascón's 54% in his last two years and on par with gascón's charging rates in 2016 and 2017. but overall charging rates can be misleading because the types of cases the d.a. receives from police can change significantly from year to year, especially during abnormal periods such as the current global pandemic. a review of charging rates for specific crime types, which allows a more accurate [...]

### Example 2b: Crime-rising theme (Progressive)

**Headline**: One year after recall, violent crime is up under DA Brooke Jenkins
**Date**: 2023-06-09
**Publication**: missionlocal.org
**Prosecutor**: Chesa Boudin (Progressive)
**Score (score_keywords)**: -0.4444
**Details**: Keyword themes: crime_rising, releasing_criminals, recall, public_safety_failure

> one year after recall, violent crime is up under da brooke jenkins crime experts agree: da has little to do with crime rates -- but jenkins said otherwise in campaign a year after the recall of district attorney chesa boudin and 11 months into the tenure of his former colleague turned bitter opponent brooke jenkins as da, violent crime is up 5.5 percent across san francisco. from july 8, 2022, when jenkins was sworn in as district attorney, until june 4 of this year, san francisco police recorded 4,870 violent incidents. during the same period the year before, when boudin was da, police recorded 4,616 violent incidents. the trend is largely driven by increases in robberies and assaults, which were higher in the past 11 months by 12 percent and 1.6 percent, respectively, according to the san francisco police department's crime dashboard. the two categories make up the vast majority of violent incidents in the city. the homicide tally is basically flat: 52 in the first 11 months of jenkins' tenure and 50 across the same period for boudin. reported rapes have decreased 9.8 percent, sex-based human trafficking has gone down by 56.5 percent, and "involuntary servitude" has gone from [...]


## 3. Aspect Sentiment (Method A)

Sentiment specifically about the prosecutor entity, not overall article tone.


### Example 3a: Most negative aspect sentiment (Progressive)

**Headline**: Don't blame Alameda DA Price for crime
**Date**: 2023-08-09
**Publication**: San Francisco Chronicle
**Prosecutor**: Pamela Price (Progressive)
**Score (score_aspect_sentiment)**: -0.9317

> don't blame alameda da price for crime the pandemic changed everything, and we failed low-opportunity communities, especially our youth; crime in our cities has climbed in some areas and it is frightening. to suggest that alameda county district attorney pamela price, on the job less than a year, is to blame for our regional public safety crisis is unreasonable. at a recent community meeting in the north hills neighborhood of oakland, condemnations were hurled at price and the police for hours. standing up as an emeryville city council member, i reminded those present what most politicians don't -- to hold us accountable. as lawmakers, we devise local public safety policies and instruct the police force. as electeds who spend your tax dollars, we failed to proactively update our crime-stopping systems by not deploying modern tools to intervene against modern crimes and failed to fund proven preventative models. some cry "defund" the police; i call it bureaucratic short-sightedness, and this is the result. since we as leaders, past and present, failed to uphold our constitutional oaths, price is now being pressured to break hers and the law by prosecuting based on insufficient evidence or circumventing ballot measures approved by public majorities. [...]

### Example 3b: Divergence — negative sentiment, neutral keywords

**Headline**: Data shows Chesa Boudin prosecutes fewer shoplifters than predecessor - The San Francisco Examiner
**Date**: 2021-07-09
**Publication**: sfexaminer.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (score_aspect_sentiment)**: -0.3401
**Details**: Keyword score: 0.0000 (near zero)

> data shows chesa boudin prosecutes fewer shoplifters than predecessor - the san francisco examiner 'we made an intentional decision to prioritize crimes involving violence, injury to human beings and use of weapons' as videos of brazen retail thefts in san francisco draw national attention, the examiner has obtained new data showing that district attorney chesa boudin is prosecuting far fewer shoplifting cases than his predecessor. the numbers show the prosecution rate for shoplifting cases involving a misdemeanor petty theft charge for a loss of $950 or less fell under boudin, from 70 percent under former district attorney george gascon in 2019 to 44 percent in 2020 and 50 percent as of mid-june 2021. prosecutors filed charges in 116 of 266 cases presented by police involving petty theft in 2020, compared to 450 of 647 cases in 2019, according to the data provided by the district attorney's office. on the other hand, the prosecution rate for certain organized retail theft cases remained between 81 and 84 percent under both gascon and boudin between 2019 and 2021. the office charged 35 of the 43 organized retail theft cases presented in 2020, compared to 21 of the 25 cases in 2019. the numbers [...]


## 4. Cross-Method Comparison

The same article scored by multiple methods, illustrating how 
different methods capture different dimensions.


### Example 4a: Multi-method negative (Progressive)

**Headline**: A terrifying murder on a quiet street highlights California's blame game over crime - The San Francisco Examiner
**Date**: 2021-09-29
**Publication**: sfexaminer.com
**Prosecutor**: Chesa Boudin (Progressive)
**Score (composite_bias_score)**: -0.5645
**Details**: All scores: score_keywords=-0.111, ta_composite_score=7.810, score_aspect_sentiment=-0.669, score_stance=-0.663, score_doc_sentiment=-0.727

> a terrifying murder on a quiet street highlights california's blame game over crime - the san francisco examiner in early september, a man broke into a house on my street and murdered kate tibbitts, 61, after sexually assaulting her. he also killed her two dogs, ginny and molly, before setting the house on fire. police quickly arrested troy davis, a 51-year-old parolee with a lengthy record, for the crime. if this horrific murder had occurred in san francisco, district attorney chesa boudin's critics would be using it to fuel the ongoing recall effort against him. but it happened in sacramento, where i lived for the past two years, and where few blame the local da for crimes. instead, scott jones, sacramento's pro-trump sheriff, blamed "liberal, anti-public-safety policies." in reality, it appears that jones' department may deserve some blame for releasing the man police suspect of killing tibbitts. a sheriff's spokesman initially blamed davis' release on a "zero bail" law the california state legislature passed in 2018. the law would have eliminated cash bail, replacing it with a system to keep people behind bars based on the risk they posed to the public. however, voters rejected the law in a 2020 [...]

### Example 4b: Multi-method neutral (Traditional)

**Headline**: Suspected mom of newborn left in Wisconsin field arrested
**Date**: 2023-03-28
**Publication**: sfgate.com
**Prosecutor**: Brooke Jenkins (Traditional)
**Score (composite_bias_score)**: 0.0000
**Details**: All scores: score_keywords=0.000, ta_composite_score=0.000, score_doc_sentiment=0.000

> suspected mom of newborn left in wisconsin field arrested the 39-year-old whitewater woman was arrested friday, the whitewater police department said in a news release posted on its facebook page. the woman, whose name wasn't released, was being held in the jefferson county jail. charges of concealing death of a child and resisting or obstructing an officer were being forwarded to the jefferson county district attorney's office, police said. the newborn boy was found march 4 in a plastic bag inside a cardboard box, wrapped in a light-colored shirt and wearing no additional clothing, whitewater police chief daniel meyer has said. investigators believe the child was placed in the field less than 48 hours before he was found, meyer said.
