2018-04-17 09.35 Software Validation - assistance from Branko ECN Items BOMs Routes

0:00
Yeah, I can see you're moving.

0:02
Yeah, OK.

0:04
Just I did send you via email PDF of just the the reason why we're doing this.

0:11
I think you probably know it.

0:13
Anyway, to cut a Long story short, this is this document.

0:18
Here is the project initiation document for the project that's focusing on Movex and Stagile software validation.

0:26
The executive summary basically puts it in a nutshell and that is we have a big recertification audits mid July or sometime in July and the ISO 13485 version 2016 is due.

0:47
My understanding, we've just had surveillance audits in the interim years, this one, they've pretty much known that the standards changed in 2016 to focus more on software validation.

1:01
Hence, we've skirted this a little bit.

1:03
We've focused on software validation of MES and then MTS.

1:10
Yeah, and now our numbers come up.

1:13
So that's why we needed your time today.

1:15
So you can read that if you want.

1:17
You probably already know it, but that gives you a bit of background.

1:21
The project?

1:21
Yep.

1:21
Yep.

1:23
OK.

1:23
OK, Don, what were you going to say?

1:29
Sorry.

1:30
No, I just said OK, that's cool.

1:34
Now shall I share?

1:36
Let you take over the screen?

1:40
Yeah.

1:42
Or send it to your screen.

1:45
Yeah.

1:46
Can you view?

1:47
Can you view my screen?

2:03
Where can we do the choice of screens?

2:07
Do I have to do it?

2:09
Here we go.

2:10
Here we go.

2:18
Didn't really show you.

2:19
Can you see it there, John?

2:26
No, it's not sticking out.

2:34
That is weird.

2:34
Audience view colour I want had left.

2:42
So can you see my screen?

2:45
Go here we go.

2:46
OK, we're in.

2:50
Alright, cool.

2:55
So we're going to do this in a test environment.

2:59
Yeah, Yes, if we can.

3:02
Franco, when you have a new product engineer, join your team.

3:08
Yeah.

3:08
Do you have work instructions or something on SharePoint or somewhere else that you give them as a guidance or is it training by, you know, buddying up?

3:25
There are SOP's with instructions on the DMR, yes.

3:32
But yeah, mostly I think they learn by training.

3:38
But yeah, there are probably, I've seen those.

3:42
They don't go into specific detailed.

3:45
Yeah, no, they don't go into screens and things like that.

3:48
OK.

3:48
I just wondered where, if there's somewhere else.

3:51
I mean, there's great background notes on the processes and I think there's some control documents on that.

3:57
I just wanted to know if there was any material you hand over.

4:00
Anyway, I'll let you take over.

4:04
I'm not sure what my password was for the test.

4:11
Would you have set it up as welcome?

4:13
I want John.

4:15
Oh, yeah.

4:19
I mean, we can, I can go back in and and create a new 10.

4:24
Just change his password.

4:28
Can we do that?

4:29
Can you, can you do that in the test?

4:30
Yeah.

4:31
OK.

4:31
We're just going to pause.

4:36
Yeah.

4:50
Bingo.

4:51
We're in alright, We're in alright.

4:54
So I've set up some templates.

5:03
Let's close this.

5:08
So the first step in creating part numbers is to upload items using the item upload template which is Excel.

5:24
So I've created three part numbers.

5:27
Part number one.

5:30
Sorry, sorry, this is for any if there are components already on Movex, obviously you wouldn't include this, but this is for the actual finished good and the components.

5:42
Yeah.

5:42
So this is assuming it's a brand new upload and no part numbers exist yet.

5:47
Yeah, OK, OK.

5:49
Is new item true, true, true.

5:51
OK, yeah.

5:53
So the first row 2 is the BOM number and then the other two rows is components, a PCB and a resistor.

6:06
OK.

6:07
So yeah, we basically populate this template.

6:11
The dark blue, the columns with the dark blue highlighted cells are mandatory.

6:21
The light blue is for engineering to fill in.

6:25
And then if we go across, yellow ones are for purchasing to fill in, but they can be left blank.

6:35
But the dark blue are required.

6:37
So I need the ECN number now to put in column A.

6:41
So I have to go to Starguile ECN request, request ECN, and then create a new ECN.

6:53
Yeah.

6:54
So we'll call it validation test ECN 1.

7:08
Customer put SRX and then you have to put the approvers, so I'll put myself for notification doc.

7:31
Document control is mandatory in the ACN, so I have to put a name down, so I'll just put myself for that.

7:40
Yep.

7:41
And production engineer, I'll put myself.

7:44
I mean, control would normally be from QA.

7:48
It'd be two, wouldn't it?

7:51
Sorry.

7:53
Yeah, it would be two dam normally, wouldn't it?

7:55
For document control, Yeah, yeah, two.

7:57
Yeah, OK.

8:00
And then, yeah, create ECN.

8:03
See, there's a lot of screen there that you jumped past, isn't there?

8:13
That's yeah, that's all stuff that we need to populate in like tells everyone what actions need to be taken, but it's nothing to do with actual Star Girl updating Movex.

8:30
OK.

8:31
Oh, OK.

8:35
But is it to do has, does it have anything to do with the quality control though?

8:40
So like for example, you've got here SMT programme and profile cheques.

8:46
If yes, SMT engineer must be included for approval.

8:50
So if the ECN effects SMT components, you need to include SMT engineer so that they update the programmes and then you would select yes and they would get the ECN and they would take actions at their end to update the programme.

9:09
OK, for the purpose of this validation process, I'm not I know you're not doing it with this test.

9:14
Could you just talk us through each one so understand SMT what's the the next one?

9:22
Yep.

9:22
So SMT then you've got test engineers.

9:26
So if you if we've received a new firmware or test procedure that needs updating, then we would select yes here and test engineers would do their thing, production engineering procedures to be updated.

9:43
It's yeah.

9:45
Anything for production engineer to do.

9:48
So is that online password, online PDP or?

9:54
Yeah, or any standard operating procedures for equipment, anything like that?

10:05
Yep.

10:05
So do you put the person responsible, do you put their user ID or something in those white spaces?

10:11
No, it's just for comments.

10:12
So basically select according to our procedure, we have to select yes or no.

10:19
So if it's not applicable, no.

10:21
If it is yes and then we can write comments like procedure needs to be updated.

10:29
Then there's a little complete thing here that you pick once you've done it, OK, It's good practise to put your initial and date in here when you've done it, just so for record purposes.

10:45
But yeah, but none of this stuff is mandatory.

10:49
Like it doesn't, you don't need to do it.

10:54
And we aren't, we only use, we don't use most of these screens we don't use.

11:00
So the main ones we use is SMT, the firmware P procedures.

11:08
We don't normally use documents to be issued to shop floor.

11:13
We used to use but we don't use now because we have online PDP.

11:18
Yep.

11:19
Mm hmm.

11:20
So before it used to be hard copy that had to be issued.

11:23
Yes, validation verification may be required for medical customers.

11:33
Well, as this is an ISO to do with medical.

11:36
So for example, would that be, you know, if you're doing Cook medical, you put be he, do you date the comment or do you just do BP and then validation needs needs to be done or something like that?

11:51
Yeah.

11:51
So if the, if there's a change to for example, the test equipment, then you might need to revalidate the equipment.

12:00
So you put a comment need to revalidate functional tester for Cook and then once it's done, you would click the tick to complete and just put your initial name and date and that would be it.

12:20
Yep.

12:22
OK, fantastic.

12:22
Thank you.

12:24
And then the next one production first article required.

12:28
We don't use that supply reference sample required.

12:32
We don't use that documents to be issued to receiving.

12:37
We don't use that because it's all online OK documents to be issued supplies.

12:44
We do use that one.

12:46
So if we get new PCB file or drawing, we will put a comment in there that this drawing needs to be sent to supplier and then document control would be the one that would take the action and send the drawing to the supplier and put their comments in there.

13:10
OK.

13:13
The next one, inform customer on implementation date.

13:17
We don't use that.

13:19
Provide the affected first serial number, we don't use that and the Section 2 we don't.

13:29
We only use the first one, which is current work orders affected, which usually is yes.

13:37
So that is for the planner to know whether they need to update the existing manufacturing orders.

13:48
So we might have a change to the BOM and oh, OK, OK.

13:54
The MO does not get updated by the when you update the BOM.

13:59
So so this is like a a work in progress MO if it needs to have the the bomb updated type of thing if it's or is it yeah, it's like it's like the break point.

14:12
So is it current all existing M OS to be updated or only update MO such and such OK or from July on or something?

14:25
Yes, yes, things like that.

14:27
Yeah, OK, that's good.

14:33
And we don't really use the rest of the fields after that.

14:41
Yep.

14:42
So that's basically it.

14:44
And then at the bottom you've got four, yes, buttons, View items, view Boms, view MPNS and view routes.

14:55
You can go into those and directly enter the data or we can use the Excel template to upload.

15:04
So you we've got both options.

15:06
So if you've got a lot of part numbers to do, it's easier by Excel.

15:11
If you've only got one or two items, then usually we just go directly in here and enter the data directly into Starguile.

15:19
OK, I suppose it's a pain to do both procedures for us.

15:27
It wouldn't be appropriate.

15:29
You've you've created your test data.

15:30
That's OK.

15:31
I think we can work it out.

15:33
We I can do example for a MPN because that's the one we mainly use.

15:40
OK, because I, I didn't create a template for MPN upload, so I can add that in manually later on.

15:47
Yep.

15:48
Yeah, OK, understand.

15:51
So I need to grab this ECN number and put it into my template.

16:03
No way the system knows where to which is sent to load the this data into.

16:11
Now do you want me to put in any purchasing parameters so that you can see that they've been loaded into Movex?

16:19
Put it.

16:20
Just put a buyer in mate.

16:21
Just put STEHST EE H Yeah, yeah.

16:29
And for the next one, yeah, that's and.

16:31
And what about the price?

16:36
Yeah, let's say PCPCB is usually 20 days.

16:40
Resistor could be 50 days.

16:44
Yep, price 550 and 0.02.

16:53
Usually we have all the multiple which is a pack size.

16:56
PCB is 1 resistor, could be 5000 on a reel.

17:01
Yep.

17:01
Yep, minimum order quantity PCB might be 100 resistors might be 5000 currency.

17:15
We'll put one as USB and one is AUD and yeah, that's about all.

17:27
OK.

17:27
Supplier can't remember the supplier codes.

17:34
Would they be in?

17:38
Yeah, I can, I can get.

17:40
We don't know what's in the text, do we?

17:43
We can have someone like SA 015 or something like that.

17:47
Well, you we know what's in in a template because under column N is the template item that we're.

17:57
Oh yeah, yeah, yeah.

17:58
So whatever's in.

18:00
So if if you leave any of these fields blank, whatever's in that template will remain.

18:05
OK, Whatever we populate, we'll get over.

18:10
OK, I didn't know that.

18:11
OK, that's good.

18:13
OK.

18:15
So it's, so it's sort of backfields whatever is left blank on this Excel spreadsheet, it will fill in mandatory fields or whatever from those templates.

18:27
Yeah.

18:27
So this this T final assembly D is a part number on Movex existing part number.

18:35
So what it does is it copies that part number and then overwrites the any data with whatever we put into the template.

18:46
That's basically how it works.

18:48
Is it only production engineers that do this?

18:53
Does anybody else this to the item master?

18:59
Yeah, the so the shared services group in Malaysia, they can do this, right?

19:11
Yeah.

19:12
And production engineers.

19:13
Yeah, OK with you, Franco.

19:18
John, for the for the purchasing fields in yellow, do you normally go and talk to the buyers and get the information from them before you fill the template out?

19:30
So normally we would fill in the engineering fields.

19:39
Yeah, yeah, OK.

19:40
And then we would send the template to purchasing to put in the purchasing data and I would send it back to us for upload.

19:50
OK, gotcha.

19:51
Understood.

19:52
Yep.

19:55
And let's put future, say, feature 116.

20:17
Alright, so that's all the fields done and you don't have to left justify or do anything like that.

20:27
No, no, I just thought the reorder point.

20:34
That's actually the wrong that's the wrong call supposed to be supply.

20:43
So OK, so you don't have to left justify 8004 that that wasn't my question.

20:50
The the uploading.

20:51
I don't think so.

20:53
OK, that's good find find out shortly.

20:56
OK so I saved as oh I'm sorry, text tab delimited.

21:14
And before I do that, I'll just save my template in case I need to go back into it.

21:19
Save as text tab limited.

21:25
OK yes.

21:28
And then I will have a text file, Yep, which I then upload via the Star Gull under Navigator ECN.

21:44
Upload ECN items and you don't have to close the request.

21:50
ECN doesn't matter.

21:53
No, no, it doesn't matter.

21:57
Select Browse to find your file, select the text file, open and then click Upload.

22:10
And then if all is good, it will say the uploading of Asian items was successfully.

22:18
Now is it are those text files?

22:21
Do they have any naming standards that they kept anywhere or is it just a once off whoever the user is, they've they've loaded it.

22:30
The data's in there, you know, all good.

22:32
Yeah, it's, we don't usually keep them.

22:37
Sometimes we can keep them, but we can check all the data by going back to the ECN and then we go to view items and we see that it's loaded in here.

22:54
And yeah, if I click on one, all the fields that we enter the populated in here.

23:01
Yeah, Procurement group.

23:03
Yeah, yeah, yeah, item group.

23:05
So yeah.

23:07
So like I said, the Excel template is just to make it easier to upload large amounts of data, but you could just manually enter all this data in here, or I can modify the data or in here if I want.

23:25
So when you were on the other screen and it had a view item, this is where it would take you.

23:36
That takes the screen and then you click on one of the items and then it opens this centre.

23:41
OK, give you the detail.

23:42
Yep.

23:43
OK, so I've I've added the revision in the description here just to give a bit more detail.

23:54
Then you can update.

23:54
OK.

23:56
And if I wanted to add another line manually, I could click create and then I could, yeah, just put in all the details, put in another part number manually.

24:16
OK, So has that gone to Movex yet that those 3 new items?

24:19
No, no, it's only in in the in this ECN at the moment.

24:25
OK mate.

24:26
So how do I get into the test?

24:32
Into the test Movex?

24:35
Yeah, you'll need to close your tabs down here and then and up from the command box, type in CMP 300 300 Yep, 300.

24:58
Hit the run button.

25:02
Yes.

25:03
And it says Are you sure?

25:05
Yes.

25:07
So now you're in companies 100, you're in the test environment.

25:11
OK, So if I type this number in, it doesn't exist yet.

25:28
OK, I can see that's not there yet.

25:31
And you can see that this number, which is our template item is here and you can see the description is T sub SMD item group, procurement group.

26:01
And all this data will be overwritten with whatever we've put here.

26:05
PCAPCBA.

26:07
Yeah, yeah.

26:08
Gotcha.

26:09
So they'll copy, copy this part number and this can be done manually in move X by selecting right click copy and then you can create another number.

26:24
And that's basically what what Stargard is doing.

26:28
Yeah, I understand.

26:29
Yeah.

26:32
But the preference is to have the engineer change note history and trial, isn't it?

26:42
Yes.

26:42
Yep.

26:43
But sometimes for.

26:47
Yeah, for for like if we've got a say we receive a ECN to add 1 new part number to a BOM.

26:56
If we followed the full star Gault process, you have to create one ECN to create the number and then another ECN to add the MPNS and update the BOM.

27:08
Whereas what we can do is pre create the number in Movex by using the copy command.

27:16
Yes.

27:17
And then just do one ECN where we populate in all the other fields and MPN and you still get the traceability, but you don't have to do 2 ECN, OK.

27:32
So we sometimes use that option, OK, to save, to save time.

27:37
Yeah, yeah.

27:39
And that's OK, obviously for auditing reasons or whatever the, the key driver was behind the Ecns.

27:47
Yeah.

27:48
Because you, you can still enter all the data under view items in the ECN and you'll still get all the.

27:55
Yeah, all the traceability history.

27:57
Yeah.

27:58
Just saves, saves us doing 2 Ecns.

28:00
Yeah.

28:01
Yep.

28:01
No, no, I get it.

28:02
Thank you.

28:03
All right, so because this number doesn't the three new part numbers don't exist yet in Movex.

28:12
Therefore, I can't do BOM updates or MPN updates.

28:17
So I need to release this ECN first to create the part numbers.

28:23
So I will approve this ECN.

28:28
So you're OK for me to do the approval now?

28:32
So any more questions?

28:35
Did you get an automatic email to to trigger that this?

28:43
Yes.

28:43
Can you see my email?

28:46
Yes, can now.

28:48
So, yeah, could you just open it up?

28:51
This is just for the purposes of the validation, please.

28:55
Yeah.

28:58
And does it provide you a link or you just know to go into Stardust?

29:02
There is a link there, a login screen.

29:06
OK.

29:06
I've never, I've never used the link, but yeah, just goes to login.

29:10
We'll take you to the login screen.

29:12
Yeah.

29:13
OK.

29:13
Thank you very much.

29:15
That's it.

29:15
And yes, I'm OK for you to prove it.

29:19
OK, so I can't approve from this screen because this is just the request ECN screen.

29:27
I have to go to my work list and any Ecns which are currently waiting for you to approve will be in in your work list.

29:41
So it's the top one tells you the title and what stage it's at.

29:50
Yeah, yeah.

29:55
And the at the top you've got the status.

29:57
So status 10 is initiation.

30:00
OK.

30:02
And then if I click approve, it will, because I haven't selected anyone for approval.

30:10
The next process it will go to is Dock Control at status 25.

30:16
And after that we'll go to dock control again at status 35.

30:22
And then I've ticked myself a notification at status 60, so after that will come to me again.

30:30
Why did you say 35 instead of 45?

30:35
Those are two men.

30:39
Those are two mandatory fields for dock status, for dock control 25 and 3535.

30:48
OK, I'm going to be a while.

30:56
I understand 45, but not 35.

31:02
Sorry, Karen, I've just got Sam standing here.

31:06
Can you just hold on one minute?

31:08
I'll pause.

31:09
I'll pause.

31:09
Yep.

31:10
Yep.

31:11
Thanks.

31:12
Paul, can you see the flow chart on my screen?

31:16
We can see you clicked it.

31:17
There's just a little bit of a delay now.

31:19
We can, yes.

31:21
Yep.

31:22
So those are all the statuses.

31:27
It's a bit.

31:28
It's not very sharp, but hello.

31:32
Yeah.

31:32
So can you see status 25 document controller?

31:37
Yeah, Yep.

31:39
And then the next one is 30 and then after that 35 document controller again.

31:45
Yes, I just didn't see it on the ECN where there was picked and with a name, that's all.

31:52
That's that's where I've got.

31:53
Yeah.

31:54
So, so dock control is mandatory.

31:58
So it's not optional.

32:00
It's not listed in there because it always goes to status 25 and 35 whether you like it or not.

32:07
Thank you.

32:08
OK, so that explains it.

32:09
So the ECN role 35 is a different thing.

32:13
The status yes, the the, the status and the role.

32:19
So role is just like 30s purchasing and it's always 30s purchasing, 20s programme manager.

32:29
That's the role numbers and status is the ECN status.

32:34
Yeah.

32:34
And the mandatory ones that you've just shown us in a slow chart aren't showing up here.

32:40
The ones that are just showing up there are the ones additional extras if you want.

32:46
Is that.

32:46
Yeah.

32:46
So the ones showing up here will.

32:49
It will only go there if I put a tick now I get it Totally.

32:54
So glad you showed us the process flow.

32:57
Thank you.

32:57
Yes.

32:58
OK.

32:59
So I've only picked production engineer for notification at status 60.

33:05
So it'll therefore it will go to status 25, then 35 and then sixty.

33:12
OK, fantastic.

33:15
So it's a status 10 now.

33:17
Once I click approve, it should go straight to status 25 Approve and you'll get another email.

33:26
Yeah, because I'm put myself as dock controller, it'll come to me if I put 2 as dot control, I would not see this easier now.

33:35
It would be in Two's worklist.

33:38
Yep.

33:38
OK, gotcha.

33:40
Could we just flick quickly?

33:41
We don't.

33:41
You don't have to open it up, but just for the purpose of to your email.

33:46
Sorry.

33:48
Email.

33:49
Email.

33:49
Yeah, Yep.

33:50
So I've got a email.

33:53
Yeah.

33:53
There you go.

33:54
Thank you.

33:55
That's all I want to see.

33:55
Thank you very much.

33:57
Yep.

33:57
I know you probably do this in your sleep.

33:59
So yeah, I just, I just delete the auto, delete the email.

34:11
Yeah, we get into you.

34:15
OK, so now it's at status 25.

34:22
Yep.

34:22
I'll just click approve again and it comes back to dock control at status 35.

34:33
And if I go back to the flow chart, you can see here status 50 is Movex update or Movex system update.

34:45
Yes.

34:45
So that's the point where the data gets sent to Movex.

34:51
OK, so we're at 35, so Movex know about it at the moment.

34:56
That's right.

34:56
So once I click approve, it will get go to status 50, it'll start updating Movex.

35:04
Sometimes that can take a while, sometimes it's very quick, depends on how much data is being written.

35:11
And once that's completed it will go to the status 60.

35:18
That must be where it makes connections through the API.

35:20
It is.

35:21
Now we had remember we had that problem with the API and a while ago, Frank, it was involved and and we did have I think was a mass change.

35:35
Was it for that was driven by Ivy or something And we found that some things weren't going through.

35:41
Do you remember that?

35:42
Yeah.

35:42
Is that, was that a corruption to the API or something?

35:44
No, no, there was no transaction.

35:49
Confirm Miguel's programming.

35:53
He would send it, but he never did a check on.

35:56
Did you receive it?

35:57
Did you receive it?

35:59
There was some.

35:59
And you remember Suzanne said this should never have worked in large patches or something anyway.

36:07
So what time, what's an average size and how long do you generally wait?

36:18
So just simple Ecns like changing, updating a BOM or MPNS.

36:28
It's only seconds or minute, but when you're creating new part numbers, it takes roughly maybe 1020 seconds per part number.

36:44
OK, Yeah.

36:45
So you can sort of see if you go, like if you're creating a hundred part numbers and you go to Movex, it can type the first number on the spreadsheet in and you can see it's created.

36:58
And then if you refresh the screen a minute later, there'll be another few numbers created.

37:04
So you can see how it's creating the numbers gradually.

37:08
It's creating record by record by record by record.

37:10
So, yeah, I wonder if that if that speed improved once we went from the AS 400 to the Power 8, but it used to be slower.

37:21
Do you know, Franco?

37:25
We we we improved, yeah.

37:28
I haven't done a like big upload recently to, I mean, we've the upgrade the power 8 I think for the end of 2016, but you know, it's a much bigger, faster box.

37:42
And we've also increased the, the tunnel that, you know, the the comms.

37:46
But anyway, it may be just part of the, the way it's coded.

37:50
So who knows?

37:52
Yeah, well, purchasing would be able to tell you because they do mass updates every week of purchasing parameters and that always took a long time.

38:03
OK Do they use ECN for that?

38:07
I believe so.

38:08
They use the same template.

38:11
They just leave everything blank except the purchasing fields update.

38:18
So if they want to change the buyer, say one of the buyers leaves and they have a new buyer, they just identify the items and then put the new buyer code in for those items on an ECN and upload it.

38:31
Yep.

38:31
Everything else you leave blank and it won't modify those fields.

38:36
Yep.

38:37
Yeah, I understand.

38:38
Yeah, very cool.

38:39
OK, OK, thanks.

38:41
OK, it's handy.

38:42
Alright, so I'll approve this ECN now.

38:48
I'll just go back to Movex to show that the numbers don't exist yet, and then I will approve.

39:01
For some statuses you have to put in your Star Gold password.

39:09
Yep, I saw that on the flow chart.

39:11
So a yellow, I think.

39:13
Yeah, so quick, quick approve now.

39:18
Can you just tell me why does it go to a document controller at this stage to approve?

39:26
There it is.

39:26
There it is.

39:27
Yeah.

39:27
Yeah.

39:27
The first time you can see as the second one, as the third one.

39:33
OK, So it didn't take too long, Few seconds for each one.

39:37
Yeah.

39:38
Yeah, that's good.

39:41
Sorry.

39:41
What was your question before?

39:44
You know, why does it go to a document controller to approve this interim thing?

39:51
Like wouldn't the product engineer be the key person?

39:57
You know, what is it?

39:58
What, what's the checking mechanism here that that requires a document controller to sign off 2 times?

40:07
I have no idea.

40:10
That's just something that was implemented long ago.

40:14
Probably something some process they had in Perth.

40:17
Understand, Mina, But for us, for us, it's just.

40:23
Prefer not to have it, yeah, yeah, just delays the ECN.

40:30
Yep.

40:30
So part numbers are created.

40:34
If I show you will see that descriptions updated the item group, product group, we should have the purchase price here, 550 and US currency supplier numbers there.

40:59
Yeah.

40:59
And if we go, we didn't have to let you justify the supplier number.

41:06
Yeah.

41:07
And if you go to the warehouse screen, you can see the supplier, Yep, the lead time 20 days, your buyer will be in here as well.

41:18
Yeah, I mean MOQ, Yeah, or the multiple.

41:24
The multiple, yeah, buyer very nice.

41:31
So Yep.

41:35
Alright, so now it's come back to me because I've ticked myself a notification, a status 60, right.

41:45
So you'll have another email.

41:47
Yep and once I've done whatever I need to do I will click approve.

41:55
Could you just sorry go to the email just so we can see what it looks like again, please.

42:00
Yep so got 1 so at status after status 50 you get a move X updated successfully email.

42:10
OK, Yep, I got 2 because one goes to dock control and one goes to the initiator.

42:19
Oh, right, thank you.

42:21
Yep.

42:23
And then this email to say that status 60, I need to take some action and then because I approved and there's no further approvers, it's easy and complete done.

42:42
And once once it's complete, you can no longer edit.

42:52
Oh, you can maybe in test you can, but in the Live 1 you can't.

42:57
Oh, everything is greyed out.

42:59
Yep.

42:59
So you can't edit anything.

43:01
Yep, Yep, Yep.

43:04
OK, thank you.

43:06
So now that's done so the next step is to upload.

43:19
So the I still can't L load the BOM until the BOM part number exists in PDS 001.

43:32
So when you're loading a new BOM, you have to do 3 Ecns, 1 to create part numbers, a second one to load the routings which will create the BOM in PDS 001.

43:47
So this is another.

43:49
OK, yeah.

43:51
So the routing, the routing creates the the parent code in in PDS 001.

43:57
Yes.

43:59
OK.

43:59
But this is an this is another step where we use a shortcut sometimes by manually creating it in Movex.

44:09
Then we can do it in one ECN.

44:12
We can load routings and bombs and everything.

44:21
But again, if you had 20 bombs to create, that might be too hard to do manually or too time consuming.

44:29
Yeah, yeah.

44:29
If it's if it's a lot, then yeah, you wouldn't do it, just do it by ECN.

44:35
But when you said 20 bombs, John, that would be for 20 products.

44:40
Yep.

44:40
But what would you use one ECN or would you use one like 1 ECN for every product or one ECM for 20 bombs?

44:50
Well, if you have to do it via the route template first, I'm, I'm not sure.

44:53
I have to have a look at what the route template is telling us, whether you can, whether you can put 20.

44:58
Yes you can do as many as you want.

45:01
OK so we can upload multiple Boms and routes in one ECN.

45:08
OK, cool.

45:10
So this is the route template.

45:13
So I can, I could copy this, paste it here, change this stock code to two and load the routing for a second BOM in one ECN.

45:30
Yeah, mate.

45:30
Gotcha.

45:31
I just have to Yeah, gotcha.

45:33
Yeah, continue these numbers.

45:34
Yeah.

45:36
OK, very good.

45:41
So I need to create another ECN for my ECN ID.

45:45
So create that request that ECN again request.

45:51
Yep, validation next number in sequence 24774.

45:59
Yeah, it automatically assigns the next available number.

46:05
If at this stage you click previous, then that easier number just disappears and can't be used again.

46:20
Customer, is that a bug?

46:25
Why did you mention that?

46:26
Is that just just for your information?

46:31
Yeah, Yeah, that's how it was designed.

46:33
Oh, OK.

46:34
So it's like locking an ECN.

46:36
So if you locks the number in.

46:38
Yeah, Yeah.

46:39
And then I think because another person might click create straight after and we'll have the next number.

46:46
But if you if you click create, it'll save it.

46:53
But if you click previous it that number just it can't be used anymore.

46:59
OK, get it.

47:01
I got it.

47:02
Yep.

47:07
So I'll just for this one, I'll just put dot control or do you want to see any other status?

47:22
No, that's fine.

47:23
That's, I don't think that's.

47:25
Yep, Yep.

47:27
Because you've explained the first thoroughly, I think we can zip through this one.

47:31
Yeah.

47:32
Yeah.

47:33
So create.

47:40
So then I can put my ECN number in here.

47:44
OK.

47:45
Yeah.

47:45
I got a question for you coming up.

47:48
Yep.

47:49
In your runtime column, not every work centre is used.

47:56
When we're making a bomb, we're doing something.

47:59
So do you put zero or do you just leave them blank for the runtime?

48:06
I put zero.

48:08
I think you can leave them blank.

48:09
It will still be 0.

48:12
OK, but normally we put zero.

48:14
Yeah.

48:15
And we don't use setup time or lead time offset.

48:19
No, no, I've not seen those in bombs.

48:23
OK, just asking the question.

48:27
Yep.

48:28
So I'll just put some dummy times in here and then the zero and report work centres at the bottom are used for the backflashing.

48:37
They control backflashing of of routing of operations.

48:46
So I'll save this, then save as text tab delimited.

49:02
I'll just go to Movex and show that that number doesn't exist in PDS 001 yet.

49:14
And then I go to Stargull, upload ECN routes, browse, select the text file, click upload and I got a error message.

49:36
OK, So what happened there is I should put through for is new route.

49:47
OK, yeah, gotcha.

49:49
Yeah, yeah, because normally we use the shortcut and pre create the number in Movex we use false.

49:59
But because this time I haven't done that, I have to put through you know what, I'm really grateful for Branco we for our software validation.

50:08
We have to create sometimes where we make a mistake and you've just done this so that we can actually do a test case and use your screenshots.

50:18
So thank you for that.

50:20
Yeah, that's so I plan, I I planned that last night.

50:24
Yeah, no problem.

50:28
I wouldn't know whether he do or not, such a trusting voice.

50:37
All right, so I'll try it again, upload.

50:46
So this time was successful.

50:51
So if I go to ECN, Yep, there it is.

50:56
There the status 10 and Movex will have some stuff.

51:02
No, it's not in Movex yet.

51:05
It's only in Star Go because of the status 10 doesn't get to Movex or Status 50 audio.

51:12
So it's the same.

51:13
We gotta go.

51:15
Could we go through the the process flow again just quickly?

51:20
It's your video.

51:21
So.

51:23
So the ECN is at status 10.

51:25
So it's in it's in my work list.

51:30
OK.

51:31
Because I'm the initiator.

51:34
Yes.

51:35
So until I approve it, it doesn't go to the next stage, Right.

51:41
Yeah.

51:41
OK.

51:43
So I have to status, what, 25?

51:50
Yep.

51:50
Correct.

51:51
Yep.

51:51
Mandatory status.

51:52
Yep, Yep.

51:56
So before I approve, I'll always double check that the data's uploaded.

52:01
OK, so I'll go to view routes and I can see here all the routings have been uploaded and the run times.

52:13
Yep.

52:13
The times, Yep, so I'm happy with that.

52:21
So I'll click approve, it'll go to status 25.

52:31
Then I approve again.

52:35
Says the other document controller.

52:37
Yep.

52:38
So that goes to status 35.

52:43
This time I have to put the password in and when I click approve, it should start updating Movex.

52:57
If I click refresh now, the number is in PDS 001 and the routes will be there.

53:07
But then it's fine.

53:09
The routes, yeah, I'm not sure it does it one by one.

53:12
We can have a look.

53:14
Yeah, all the routes are there.

53:15
Are they here?

53:16
Yep, but no materials which are in blue.

53:23
Yeah, there's no materials yet.

53:27
So yeah, the routes with 0 just come out blank anyway.

53:31
Blank.

53:32
Which means they're they're unused work centres in in for this particular bomb.

53:37
That's what it really means, doesn't it?

53:39
Yep, Yep.

53:44
I just noticed that the zero and report work centres work there, but that's probably because it wasn't refreshing properly.

53:50
There it is.

53:50
They are.

53:51
They're now at the bottom.

53:52
Yeah, yeah, yeah.

53:54
But they're there too, so.

53:55
OK, cool.

53:58
All right, so now the we have to upload the parts to the BOM, which is the BOM upload template.

54:12
So in here we need to change the the default to to truth is new bomb no, because the number that stock code exists in PDS double O one it's yes now false.

54:34
It's not a new not consider the new bomb.

54:37
Gotcha five star goal.

54:38
Yeah, I need code on new Sen Yep, new ECN.

54:44
Yeah, I have to go to request ECN.

54:52
That's why it takes a while.

54:54
That's why we use the shortcuts to pre create new music because plenty of plenty of opportunity for the engineers as they're getting all this information together to to gather it over time.

55:07
Like might take them a few days to get all this stuff together in into the spreadsheet and before they go anywhere near Stargo.

55:14
Do you ever change the from date?

55:20
No, and you never fill in other stuff.

55:26
I think I might have tested it a long time ago, but I can't remember.

55:33
Yeah, but we don't change it.

55:39
Yeah, yeah, yeah.

55:40
We do fill in other parts.

55:42
So in ECN description, we normally write some comments about what the ECN is about.

55:49
OK, customer ECR is we put the customer's ECN number if they have one, otherwise we leave it blank.

56:00
So E engineering change what what's ER request?

56:05
Oh, OK, engineering change request number.

56:09
So this is where the customer wants to change some of the materials in a BOM.

56:13
Is that what it is?

56:16
Oh, could be anything, any, any kind of change.

56:18
But some customers will have like a formal ECN template and they'll have a ECN like we have our ECN number at the top.

56:27
They will have their own ECN number.

56:30
OK.

56:30
So we just it's just a cross reference.

56:33
A cross reference number.

56:34
Yeah, product number we put in if, if it's only affecting one bomb because you can only put in one number.

56:46
Otherwise you leave it blank.

56:47
It's not that important here.

56:51
You can pick like what what's changes are in the CCN.

56:57
So in this one, we're loading new Boms, new MPNS.

57:03
None of this is mandatory.

57:05
It's I think it's there just so you can search or philtre Ecns by these various fields.

57:15
OK, in here we put a link to DMR of where we upload the ECN approvals or or emails from customer to say that they approve the ECN.

57:30
Could you just do an example there of what you would type please?

57:35
So I would go to Star Gal, say Melbourne DMR, Airpoint, Yep, generic Ecns.

57:54
And then here we have all the ECN numbers.

57:57
So I would create a new folder with with this ECN number and then in that folder I would upload the emails or whatever approvals we have, OK?

58:14
And I would copy that link in here, right?

58:20
OK.

58:23
I think the original idea was that this next field here where you got SharePoint documents was supposed to be a link where you could upload directly, but I think it was never developed, so we have to do it this way.

58:40
Yeah.

58:41
So it'd be good if you could just drag and drop the email straight into the ECN.

58:47
Yeah, the link I'll just put put myself in dock control again and for notification create.

59:19
So now this ECN will be in my work list.

59:28
Sorry, but I just muted.

59:30
We're just commenting how complicated this is.

59:33
Yeah, but but it it is, well, I mean, it makes sense.

59:41
It's complex rather than complicated.

59:43
I think it's and it's quite involved.

59:45
It's more involved than I thought it was.

59:48
Yeah.

59:49
I mean, there's a lot of a lot of room for improvement in terms of the software and to simplify it, but it's still quite powerful, even though I agree with you, there is there is room for improvement, but it's still quite functional and powerful.

1:00:03
Well, it was what it does.

1:00:05
So what was it?

1:00:07
Spec 2020, ninth of January 2008 was the spec.

1:00:12
So it's a 10 year old specification.

1:00:14
Wow, look at that, 10 years old.

1:00:18
I've just, I've found the the original specification.

1:00:22
OK.

1:00:22
Yeah.

1:00:25
Have you seen that you you probably wouldn't.

1:00:27
Were you involved in, in, in, in the in, in development when this was being developed?

1:00:31
Were you involved with testing and all that stuff?

1:00:33
Franco with Robert Gold.

1:00:35
Robert Gold?

1:00:35
No, no, I was because it was all developed in Perth.

1:00:42
I was just, I was just sent to Perth for a couple of days to be trained so that I could train people in Melbourne how to use.

1:00:51
OK, gotcha.

1:00:52
I wasn't, I wasn't involved.

1:00:55
We'd have to ask Lynn when Melbourne started.

1:00:58
Well, you did you originally come along when Melbourne opened or was Melbourne already there when you joined the company?

1:01:07
No, I joined in when it was AMS in Keysborough.

1:01:14
What did you, it was like 2001.

1:01:18
Oh, wow.

1:01:21
That's when Movex was implemented.

1:01:27
Yes, yes, I was here when Movex was implemented.

1:01:30
Yeah, 'cause we had another system before that.

1:01:34
That's a painful process.

1:01:38
That's what they would have had, manufacturing plant in Sydney and New Zealand and New Zealand, obviously.

1:01:46
Were they 2 in New Zealand or just the 1?

1:01:47
I don't know.

1:01:48
Anyway, there's Brisbane.

1:01:50
Brisbane I also thought had a manufacturing plant as well.

1:01:52
Yeah.

1:01:53
Anyway, yeah, they did.

1:01:54
Yeah.

1:01:56
Anyway, OK.

1:01:57
Wow, that would have, would have been a big roll out back then.

1:02:03
OK, All right.

1:02:06
So, yeah, so in the BOM upload template you basically put in the the BOM number and then you put in the sequence number, operation component, quantity, designators and the update.

1:02:26
That's pretty much it.

1:02:27
Yep.

1:02:29
Designators have to be delimited.

1:02:36
Is there any limit on designators?

1:02:42
Yeah.

1:02:42
I mean, you're limited by Excel, you're limited by Stargile.

1:02:47
On the number of designators you can put in.

1:02:51
I don't think so.

1:02:53
We haven't reached the limit yet.

1:02:56
Yeah, OK.

1:02:56
If there is some of them seem to have a lot.

1:03:00
Yeah, I've seen, yeah, there's some with few 100 centimetres.

1:03:07
Yeah.

1:03:09
OK, I'll put in an extra designator here just to show that the system cheques if the quantity and designators don't match, save as a another test case that we can do this is good.

1:03:31
And it's false for new bomb because everything's already in there.

1:03:36
Yeah, understand that.

1:03:38
So what it's basically looking at is PDS 001.

1:03:42
If that bomb number exists, it's considered as not new.

1:03:47
Yep, Yep, Yep.

1:03:49
Because the route PCN has created it, it's OK.

1:03:54
So we should get an error, is that right?

1:04:00
You should get a warning because so upload ECN bombs, browse BOM, open upload.

1:04:14
So you get a warning to say that part number of the AL 12111 quantity 5 does not match the number of circuit reference 6, but but it was uploaded successfully, yes.

1:04:33
So it's up to the engineer to go and into Movex and correct that.

1:04:39
Not in move, not in Movex.

1:04:42
So in the ECN OK, refresh.

1:04:48
So status 10 still 1.

1:04:52
Yep, still 10.

1:04:54
I go to view BOMS and my 2 lines have been uploaded.

1:05:00
Yep, I can click that line.

1:05:06
Yep, I can delete.

1:05:10
If I delete one too many, it should give me another warning in here so it'll say quantity 5 does not match.

1:05:20
OK.

1:05:20
So it's a that one's a proactive or a real time?

1:05:24
Real time.

1:05:24
Yeah, Yeah, that's good.

1:05:26
Yeah.

1:05:26
Well, I said the other one is too.

1:05:29
Oh yeah, that's good.

1:05:30
That's good.

1:05:30
I like that is the operational number is always 50, isn't it?

1:05:39
It's 50 for SMT parts, 100 for through hole parts and 160 for mechanical parts.

1:05:49
It's linked with the routing, so.

1:05:51
OK.

1:05:52
Yeah, SO50 is the SMT route.

1:05:56
So that means these parts are fitted at SMT, the SMT workstation.

1:06:01
OK, good question.

1:06:04
So if I if I had another resistor which we wanted to hand solder, I could create another line manually in here?

1:06:16
Yes, put in the AL 5 deploy 1 validate.

1:06:23
Normally it displays the BOM here, but because the Bom's not loaded yet, you don't see anything.

1:06:30
OK, And then I could add another part number at operation 100 sequence 140 component.

1:06:48
What's the component?

1:06:52
So I'll use the same resistor again and quantity one quote 101 create so I can manually add another line.

1:07:14
Fantastic.

1:07:15
So this, this, we normally do this for changes.

1:07:19
We wouldn't use the template when we're updating Boms because it's easier just to go in and edit the BOM via Star goal.

1:07:29
Yeah, OK.

1:07:33
And So what I'll do, I'll also do an example of the MPN update.

1:07:40
So I'll go to view MPNS create and I will add the MPN for the PCB.

1:07:52
So here in the top it shows the existing MPNS.

1:07:57
See that there's no MPN for that number as yet.

1:08:02
So I'll put in the part number I have to put in.

1:08:08
There's a few fields mandatory.

1:08:10
1 is the manufacturer number, so I'll put Speedy, which is 8004 manufacturer part number, which is the MPN, so we'll call it the.

1:08:27
So this is Speedy's part number, right?

1:08:30
Yeah, yeah.

1:08:35
Part number 61.0 and then the manufacturer name and currency only because it's a mandatory field.

1:08:54
OK, but price isn't, sorry, the component price and the other fields aren't.

1:09:03
What about the from dates?

1:09:05
We don't use any fields.

1:09:08
Only other field we use is end effective date.

1:09:11
If we want to delete MPN, yeah we want to retire an MPN yeah yeah.

1:09:18
Is there any default one there?

1:09:20
For the default flag?

1:09:23
We use default if we want to.

1:09:25
There it is set 1 MPN as the preferred MPN.

1:09:32
Yeah.

1:09:32
But what happens if you get multiple defaults?

1:09:35
You should only set one default.

1:09:37
But what happens if you've got more than one?

1:09:40
Then it's it's alphabetical order or something I don't know, but I'm I'm bringing it.

1:09:44
Can you can set you can set more than one.

1:09:47
I'm not sure how the system like how purchasing views that they're they're totally confused purchasing view that like that they're totally confused.

1:09:59
I don't buy them, no.

1:10:01
And then they're probably going to come back to the engineer and say which one do you want me to buy?

1:10:04
Yeah, fair enough.

1:10:05
Yeah, they never, they never ask.

1:10:09
Well, they just, they just go.

1:10:10
They just, they just buy whatever they whatever's available.

1:10:14
So if they can get the default, they will.

1:10:16
If not, they'll get the next one.

1:10:18
OK.

1:10:19
Because as long as it's an approved MPN, they're allowed to buy it.

1:10:24
OK.

1:10:27
And if I guess it's, yeah, it's the business by business case.

1:10:29
If it's needed urgently and, and someone's got it, but it's, it's, it's half a cent dearer, but they've got plenty of stock.

1:10:36
And the other guy who's half a cent cheaper, but he's got no stock and we need it urgently, then the business isn't, is buy it.

1:10:44
Yeah, the the only thing they need approval for is if it's PPV, like the cost is a lot higher than the standard cost.

1:10:53
Yeah or yeah, the parts are old.

1:10:57
Yeah, if the parts are old date code, then they ask engineering for approval, but otherwise as long as it's listed as an MPN, they can buy it without any approval.

1:11:12
So we've added one MPN for the PCB.

1:11:15
Yeah, MPN the only visible in Stargall.

1:11:23
So there's no field in Movex where we can see them go to maintain MPN numbers.

1:11:31
And currently there's no MPN for this number.

1:11:40
So once I approve, yeah, when the upload NPN, so it doesn't go anywhere except for a Sagile table.

1:11:51
I'm just asking John, that's correct.

1:11:53
OK.

1:11:53
There's no native Movex table and it doesn't get loaded into a custom field anywhere.

1:12:00
OK, thank you.

1:12:01
I mean, I imagine because you could have multiple NPN in in DB, just hang on, bring in DB serve.

1:12:06
When we've replicated the native Movex tables, we we replicate the star gel MPN table to go into DV serve so that it looks like it's a native moving table.

1:12:17
Yes, I remember it's MPM.

1:12:20
Someone named it incorrectly.

1:12:21
Yeah.

1:12:21
OK, OK, sorry, Branco.

1:12:26
All right, So I will approve this ECN and prove it again 25 one more time, Yes and it should go complete password move X Yep.

1:12:54
So approve that was you entered the wrong password.

1:13:03
Thank you for creating more.

1:13:05
Another.

1:13:06
Another demo.

1:13:08
Yeah, you did that on purpose.

1:13:15
Did you think about that one last night as well?

1:13:19
That was on the fly, that one.

1:13:23
Well done, mate.

1:13:24
Well said.

1:13:24
Seems Franco's like you.

1:13:28
Always unruffled.

1:13:33
Yeah, Look in blue.

1:13:34
Yeah, look at that.

1:13:35
There's our components.

1:13:39
And hey, and now can I just make an MPNMPN Should also be visible now.

1:13:47
Yep.

1:13:50
There she is.

1:13:51
There she is.

1:13:52
We go back to the material.

1:13:53
The move X move X, Yeah.

1:13:57
Two of the components were linked to Operation 50, and there they are under sequence #100 and 120, the one that he added manually through Sagon was linked into Operation 100.

1:14:12
And see, it sits down in the Operation 100 work centres between 95 and 100.

1:14:23
That's normal, wasn't it?

1:14:24
Yeah, and it's something I didn't realise until today.

1:14:28
That's how it's stored.

1:14:29
Yeah.

1:14:29
It goes next to the route.

1:14:32
Yeah, which which is so sensible.

1:14:36
Yeah, yeah, very close.

1:14:38
I like it.

1:14:40
So S and no is a sequence number.

1:14:44
OK, OK, cool.

1:14:49
So that's pretty much it.

1:14:55
That's good.

1:14:56
And then you've got to not for this purpose of this call, but then you've got to go to MTS, yes, then we could employ like payroll is on MTS, right?

1:15:13
Yeah, which I think should be and also in also in Zala, we could upload the bombing to Zala as well.

1:15:24
Is there a way of importing into valour?

1:15:29
Yeah, we so we export using the use X reports and then import.

1:15:35
OK, so that's a little bit less painful.

1:15:38
Yeah, Yeah.

1:15:41
But MTS, it's not automated, is it it?

1:15:48
Yeah, it is.

1:15:50
There's a button that basically uploads the latest BOM or OK, as as in you, you have to, you have to do it.

1:16:00
But you it's just a one click button.

1:16:03
Yeah.

1:16:04
And and is that because you've got it may have to time it if there is a work in progress.

1:16:11
Yeah.

1:16:12
So that you may not want to make that change immediately.

1:16:17
OK, So MTS is automatic.

1:16:20
Yeah.

1:16:20
There's a store procedure called get data, and that must be what runs when they do the click.

1:16:25
OK, it goes to DB serve, gets the BOM data.

1:16:28
Yeah.

1:16:28
And then brings it into MTS.

1:16:30
That's OK.

1:16:32
Fantastic.

1:16:35
Yeah.

1:16:35
There was a screen that was in Star Gile.

1:16:39
If we could just go back to there where you were.

1:16:42
See XLS on the bottom left hand line?

1:16:46
Yep.

1:16:46
What does that mean?

1:16:47
Export it to Excel?

1:16:50
You mean this button?

1:16:51
No, no, no.

1:16:52
Can I?

1:16:52
I don't know if I Can you see if I take over?

1:16:56
Can you see my arrow?

1:16:58
No, no.

1:17:00
OK.

1:17:01
Down the just above the close button, mate, there's an XLS button.

1:17:05
What's that do?

1:17:10
Or is that the same thing as above, export to Excel?

1:17:15
It just brings the data into Excel, taking its time.

1:17:25
Yeah, there it is.

1:17:28
OK, OK, OK.

1:17:36
Thank you.

1:17:38
Is that the same as the green cross?

1:17:39
Is it?

1:17:40
No, the green cross puts a Excel within the web page.

1:17:47
OK, OK.

1:17:50
Oh yeah.

1:17:50
There you go.

1:17:53
It's like a because object linking embedding.

1:17:55
Oely.

1:17:57
Yeah, because like I want to copy the MPNI can't I can't highlight this to copy the MPN.

1:18:03
So I have to click the Excel button.

1:18:07
Yep.

1:18:07
Yep.

1:18:07
A little handy.

1:18:08
OK, alright.

1:18:11
And so the only other thing is there's a thing they call push ECN to move X.

1:18:21
Yeah.

1:18:21
What does that do?

1:18:23
Well, I think that's been when it says it thinks it's gone, but for whatever reason, it hasn't gone.

1:18:31
The API there has been, Whether there's a network failure, who knows.

1:18:36
I can remember being asked to do push an ECN in the early, early days, but I haven't been asked for years.

1:18:44
But that might be because sometimes they get stuck at status 50 and then you can use that to to push them through.

1:18:54
And what do you, what are the conditions do you think that it gets stuck at 50?

1:19:01
Sometimes if it's if you're uploading say 5000 parts or few thousand parts, it seems to get stuck.

1:19:19
But but if you're doing 5000 parts as each one is going, is it getting a message back saying I've sent you no, yes, I've received you send the next one I've received.

1:19:29
So I think this is the mod that Suzanne did, whether whether Miguel or that guy in Queensland ended up doing it.

1:19:36
Do you remember we had that train door opening this type of thing and we and it said the ECM was uploaded successfully, but it wasn't.

1:19:49
I think that's the one correct.

1:19:51
So when we went back, it was it was missing from the bomb.

1:19:54
Yeah.

1:19:55
And it was bad programming that there was.

1:19:57
When you do any EDI or use an API, you do a confirmation that you actually.

1:20:05
What you sent through did get did actually reach the it's just a normal transaction handling and that I think that was missing in but to be fair to come activity.

1:20:16
This cost of this project went got out of not to be fair on that, but it got out of hand and the project was halted.

1:20:24
That is the the utility system utilities and reporting.

1:20:30
There's a big yawning gap.

1:20:31
It was in the original spec from memory.

1:20:34
But that's why you know, the stuff you do is pretty clumsy in setting up a user.

1:20:39
There were better, there were better ideas, but they just, they, I think John Paul said, hey, you know, we're getting a candidate and the.

1:20:48
So who knows whether that was bad coding or whatever.

1:20:53
But Franco, does anyone have permission to push an ECN to, to move X or is that just you or me or do you know?

1:21:05
I don't think everyone has 'cause I know sometimes Daniel asked me to do it.

1:21:12
Yeah.

1:21:12
I thought it depends on the user setup.

1:21:16
Yeah, I, I think it's very limited.

1:21:19
So do you get asked very often or not?

1:21:23
Not recently.

1:21:25
I although we because they used to always send to Daniel.

1:21:31
Pitching is sent to Daniel to do the math updates of purchasing parameters.

1:21:36
But we've we've told pitching like asked them to do it themselves.

1:21:41
So I'm not sure if they have issues.

1:21:45
Well, I don't think, well, no.

1:21:48
And I think I do actually think it's only the admin profile that we use and Branco.

1:21:55
So, and the reason for commenting is that on the rare occasion that Branco's away, I might get asked, but it's been, I think it's been years.

1:22:05
I think it was only the first year that, that I would get asked to push it through.

1:22:10
So I think this predates AS AS400 power 8 upgrade.

1:22:18
You know, I just just my I have no science behind that.

1:22:22
It's just I did used to get asked.

1:22:25
So either branker has never gone on leave since 2013.

1:22:32
I've had plenty of leave.

1:22:36
OK, alright, thank you so much.

1:22:39
Will we is is that that's the end for for you?

1:22:44
That's everything you wanted to go over for us.

1:22:48
Yeah.

1:22:49
I don't know if there's anything else you need to see or do you need to see like modifying a bomb or Oh gosh, yeah.

1:23:00
But how much time do you want to regroup?

1:23:05
Like for another, we can regroup in three weeks time if you like to do something like that?

1:23:11
Or is it quicker now to knock us over?

1:23:15
Probably quicker just to do it now.

1:23:17
OK, I can do a quick ECN.

1:23:22
Thank you.

1:23:27
So I'll go to request ECN create would be quality impact.

1:23:38
We would have to we'd have to have a separate throughout the years we do change bombs, cool design changes.

1:23:45
They're probably the most common ECNS is bomb changes rather than bomb uploads.

1:23:52
Yeah, there you go.

1:23:55
Well then it's worth doing.

1:23:56
Yeah, because they're just as important.

1:23:59
If the customer wants a change or we have to make a change, they're very important.

1:24:03
Quality.

1:24:04
Yeah, GMP, all that.

1:24:14
Normally for BOM changes, we don't use templates.

1:24:17
We just do it directly in the ECN, right.

1:24:23
So for example, I've created the ECN, Yes.

1:24:30
So status 10, I want to change something in the BOM, so I'll go to view Boms, I'll create a I'll type in the BOM number, click validate and it will display the BOM for me.

1:24:50
Here if you wanted to quantity or what's the what's a common change?

1:24:58
Is it add?

1:24:58
Is it changing the quantity or adding, replacing a yeah, it could be add, add, delete or change is the common 1.

1:25:08
So maybe I want to delete this hand folded part Yeah, yeah.

1:25:18
So I'll select delete.

1:25:21
Basically all I have to do is select delete and it will PR.

1:25:26
But just for good practise we usually change the quantity as well, although you don't technically have to do that because it will still delete the part from the BOM.

1:25:37
Yes, without changing the quantity, yes.

1:25:41
And then I might want to make another change, which is I might want to, so that resistor that we took out of there, we might want to place it by SMT now.

1:25:57
So we increase this to 6 and add how come the deleted line's still there?

1:26:03
Is it because you haven't updated?

1:26:05
It hasn't actually actioned yet?

1:26:06
Actioned yet.

1:26:07
OK, yeah.

1:26:07
So it's, I think it's just picking up the BOM from Movex, the current BOM, Yes, yes.

1:26:14
Yep, Yep, Yep.

1:26:18
Create gives you this warning.

1:26:24
No, that's an error because the action flag should be change.

1:26:28
All right, OK, there you go.

1:26:30
Because it was thinking I was trying to add the same part again.

1:26:34
Gotcha.

1:26:34
Yeah, thank you for another test case.

1:26:38
That's good.

1:26:40
And yeah, the good thing here is that it shows you very clearly, like deleted circuit references and added circuit references.

1:26:51
So you can see here R1 O1 has been added, yes, create.

1:27:01
So I've got 2 changes.

1:27:04
Yes, delete action and a change action to happen.

1:27:07
Yep.

1:27:09
And you might want to change MPN so we can't.

1:27:24
We can't delete a MPN but you can.

1:27:29
Or you can't even change a MPN so I couldn't.

1:27:32
If I want to change this to a 1.1 I think it doesn't.

1:27:39
It doesn't let you all we all we can do is end date the MPN and then I will add a new MPN.

1:27:55
OK, so action flag add and then I'll make this revision 2.

1:28:08
OK, I have to update the sequence number.

1:28:17
So we've got one revision, one being end dated and revision 2 being added.

1:28:25
And because it's the latest revision, its start date is by default after the last one finished.

1:28:36
No start, there's no start dates.

1:28:39
It'll as soon as the ECN is approved, it'll be active.

1:28:44
OK alright.

1:28:45
And the end effective date here can be any date.

1:28:48
So if I made it tomorrow, you would still see see both MPNS until the following day.

1:28:58
OK, so that's why I put yesterday's date in.

1:29:04
So that would show that it's disappeared.

1:29:06
If I put today's date in, it would still be visible today.

1:29:10
OK, will this appear tomorrow?

1:29:17
Yep, and you can also go to view items and edit item details.

1:29:32
Too many zeros.

1:29:35
So I might want to change the description also to say Rev 2.

1:29:43
And yeah, you can change any other fields here that you want.

1:29:49
Let's keep it simple and then I will approve this ECN approve.

1:30:14
Approve and last time approve with password.

1:30:38
So now if I go to view MPNS and refresh, it's changed to revision 2.

1:30:48
OK, But if you click view all, will it show the old ones as well?

1:30:53
Yes.

1:30:59
So you can see all the old ones.

1:31:01
Look at that.

1:31:02
OK, fantastic.

1:31:05
Oh good, and if we go to move X refresh, probably have to exit now.

1:31:21
That one's disappeared.

1:31:25
How come this one didn't change quantity?

1:31:31
I thought we changed quantity, but we went to six so far.

1:31:38
Do we upload ECN?

1:31:41
Oh, here it's still under status 50.

1:31:44
So that means there's some a problem.

1:31:49
Yeah.

1:31:49
So I would have got a email saying move X update failed.

1:31:55
Oh, can we look at that please?

1:31:56
Yeah.

1:32:01
So what I can do now is I can right click on this ECN and view error log and it says the AL 1-2 already exists in product with same from date and cannot be added.

1:32:29
Is that because you've got to delete it and it has to come out first and you can change?

1:32:35
It's all we're doing was doing a change.

1:32:37
We're not doing an addition, maybe because.

1:32:43
Maybe because if I did it tomorrow, maybe it'll work.

1:32:52
Yeah, changed it.

1:33:01
Are there rules, some weird rules that they had?

1:33:04
Hang on.

1:33:05
If I change the state in Movex manually to yesterday?

1:33:10
Yeah.

1:33:10
Yeah, I can't.

1:33:13
I can't edit you.

1:33:14
Can the next one skip over to the 999.

1:33:18
Yeah, Yeah.

1:33:20
I wonder if you put a you can't put a date.

1:33:25
Yeah, it's not going to like that.

1:33:27
It's not the from date.

1:33:29
Need to edit the from date or probably if I go to the ECN and change the from date to tomorrow then click.

1:33:51
So when the ECN fails it it goes back to your work list.

1:33:59
I'll go to the dock controllers worklist and you've got this button called update movex.

1:34:07
So you have to correct whatever was the error and then you can try it again and this time it went through successfully.

1:34:23
But probably the change won't happen until tomorrow, I guess.

1:34:29
Yeah, yeah, you're right.

1:34:30
And does that.

1:34:33
And that's probably why it's saying back there operation pending because it's going to pend until tomorrow till till the actual change becomes effective.

1:34:42
Where where does it say pending?

1:34:45
Yeah, back in Star Drive.

1:34:46
I saw it.

1:34:48
That's status 60.

1:34:49
See up there?

1:34:51
No, that's, that's the standard text for action.

1:34:54
That's just the status 60.

1:34:57
That's nothing to do with Movex.

1:35:00
That's just notification for whoever you've selected under status 60.

1:35:10
Yeah.

1:35:11
Oh, I can see it down there.

1:35:12
Yeah, man.

1:35:12
OK, got you.

1:35:14
So it does it.

1:35:16
There's nothing that needs to be pushed to.

1:35:19
So it's passed successfully.

1:35:21
So the only status 50 is the only stage where Stargall is interfacing with Movex.

1:35:28
Once it's status 60, there's no more.

1:35:32
You have to assume that it's already interfaced.

1:35:36
Yes, Yeah.

1:35:37
So if there's anything, if something didn't update, that's when we'd normally come to you guys and say what's going on because we've made a change, but it didn't work.

1:35:51
Yep.

1:35:53
I would have thought this should be in moving, but yeah, maybe the from date.

1:35:59
You can check tomorrow if that change happens tomorrow.

1:36:04
Yeah, but I just can't imagine what's going to trigger that change like what's sitting in the background.

1:36:11
Like I would have thought visually you could see something.

1:36:14
Your refresh screen there, mate, Exit, go back in.

1:36:27
Nothing looks different.

1:36:29
Nothing's down the bottom like a whatever.

1:36:35
Yeah, unless, unless Targal has some other function.

1:36:43
Sorry, Where does the revision turn up on Movex?

1:36:46
Is it the bomb revision number or something?

1:36:52
So the revision is update the date and revision number.

1:36:56
What if you put in 18?

1:36:59
Yeah, at the top?

1:37:01
Oh yeah, try and do it.

1:37:09
And is it revision 2?

1:37:11
Was it No, no revision.

1:37:13
We change, we change manually.

1:37:16
So we go into PDS double O 1.

1:37:19
And in here we normally change to revision 2, right.

1:37:26
And then we put text in here, say ECN, whatever was the number?

1:37:34
Yep.

1:37:35
And then the change and Yep, Yep, that prints on the on the move X bomb on the move X reports whatever is in this text box gets printed there.

1:37:47
Yep.

1:37:48
And could you refresh again?

1:37:50
Sorry, not yeah.

1:37:55
There we go 6.

1:38:00
So I think it's made the change in move X, but movex works on the dates, so you can view old revision bombs.

1:38:08
And yeah, well, if that screen defaults to today's date, that's fine.

1:38:15
No, it's a 'cause I couldn't think what programme sits in the background.

1:38:19
I would have thought has to be in there.

1:38:21
I was gonna go and look at the table.

1:38:23
I better I I think of itself.

1:38:24
I better sitting in the table just not displaying it on the screen.

1:38:27
Yeah.

1:38:27
So change the screen, but change the screen display.

1:38:31
Yeah.

1:38:31
No, that's really good.

1:38:32
That makes sense.

1:38:33
I'm happy.

1:38:34
I was worried.

1:38:35
Yeah.

1:38:36
No, that's good.

1:38:36
That's to me, that's working fine.

1:38:38
That's how I would expect to see it.

1:38:40
I think you've covered everything and some.

1:38:43
That's great.

1:38:46
Cool.

1:38:47
I, I've only got one small question.

1:38:50
What is the difference between a product engineer and a production engineer?

1:38:56
And you know, I consider you as a senior product engineer and the other product engineers reporting to you like Shamara and used to be Charlie Twee and things like that.

1:39:08
Is that correct?

1:39:09
And so who's production?

1:39:10
Well, we, we, we are production engineers, OK.

1:39:16
I get the word in terms, in terms of the title, that's that's what we're production engineers.

1:39:24
We don't have product, we don't have product engineers, right.

1:39:28
Yeah, OK.

1:39:29
I just had heard interchanged process product and production engineers and it just just depends on who you're talking to.

1:39:37
But I've never, I've thought I can look at the job titles on, you know, on email.

1:39:43
Yeah, still none the wiser, but sounds like you all do everything.

1:39:48
Our web production engineers, yeah.

1:39:52
So basically after the looking after the products and the production process, process, process and maintenance, engineers are more looking after the equipment on the line.

1:40:12
Means and, and the process of the machine itself, whereas we're more on the product specific.

1:40:22
OK.

1:40:23
I, I guess Mihai used the word process flow in MTS, which is probably the routing.

1:40:30
I understand the routing, you know, so it's just, it's just interchangeable terms.

1:40:35
There's so many acronyms and terms.

1:40:37
It's, it's, yeah, unless you're down in the plant, you, you lose a little bit of it.

1:40:42
All righty.

1:40:43
I think we should give Branco back his day.

1:40:46
I really do appreciate what you've done.

1:40:49
It's been very comprehensive.

1:40:50
It's been fantastic.

1:40:52
Thank you so much.

1:40:53
No problem, I very much really.
