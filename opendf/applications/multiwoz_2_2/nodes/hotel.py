
from opendf.applications.multiwoz_2_2.nodes.multiwoz import *
from opendf.applications.multiwoz_2_2.utils import *
from opendf.graph.nodes.framework_functions import revise, duplicate_subgraph

if use_database:
    multiwoz_db = MultiWozSqlDB.get_instance()
else:
    multiwoz_db = MultiWOZDB.get_instance()
node_fact = NodeFactory.get_instance()
environment_definitions = EnvironmentDefinition.get_instance()


class Hotel(MultiWOZDomain):

    def __init__(self, typ=None):
        typ = typ if typ else type(self)
        super().__init__(typ)
        self.signature.add_sig('address', Address)
        self.signature.add_sig('area', Area)
        self.signature.add_sig('internet', Internet)
        self.signature.add_sig('parking', Parking)
        self.signature.add_sig('name', Name)
        self.signature.add_sig('phone', Phone)
        self.signature.add_sig('postcode', Postcode)
        self.signature.add_sig('pricerange', Pricerange)
        self.signature.add_sig('stars', Stars)
        self.signature.add_sig('takesbookings', Takesbookings)
        self.signature.add_sig('type', Type)

    def get_context_values(self, inform_values=None, req_fields=None):
        slot_values = {}
        for name in self.inputs:
            element = next(filter(lambda x: x.typename() == "Str", self.input_view(name).topological_order()), None)
            slot_values[f'hotel-{name}'] = [element.dat] if element else []

        if inform_values:
            for k in inform_values:
                slot_values['hotel-'+k] = inform_values[k]

        return slot_values

    def describe(self, params=None):
        prms = []
        address, area, internet, parking, name, pricerange, stars, type = \
            self.get_dats(['address', 'area', 'internet', 'parking', 'name', 'pricerange', 'stars', 'type'])
        prms.append(name if name else 'the ' + type if type else 'the hotel')
        if stars:
            prms.append('has %s stars' % stars)
        if area:
            prms.append('in the %s' % area)
        if pricerange:
            prms.append('%s price range' % pricerange)
        if parking:
            prms.append('with parking')
        if internet:
            prms.append('with internet')
        return Message(', '.join(prms), objects=[self])

    def getattr_yield_msg(self, attr, val=None, plural=None, params=None):
        nm = self.get_dat('name')
        msg = nm if nm else 'The hotel'
        if attr == 'stars':
            return Message(msg + ' has %s stars.' % self.get_dat('stars'))
        if attr=='phone':
            return Message(msg + "'s phone number is  %s ." % self.get_dat('phone'))
        if attr=='type':
            return Message(msg + '  is a %s .' % self.get_dat('type'))
        if attr=='pricerange':
            return Message(msg + ' is %s .' % self.get_dat('pricerange'))
        if attr=='parking':
            prk = self.get_dat('parking')
            return Message(msg + ' has%s parking.' % '' if prk=='yes' else ' '+prk)
        if attr=='postcode':
            return Message(msg + "'s post code is  %s ." % self.get_dat('postcode'))

        return Message('')

    @staticmethod
    def do_fallback_search(node, parent, all_nodes=None, goals=None, do_eval=True, params=None):
        return multiwoz_db.find_elements_that_match(node, node.context)

    # disabled fallback_search  - do we need it??

    def generate_sql_select(self):
        return select(MultiWozSqlDB.HOTEL_TABLE)

    def generate_sql_where(self, selection, parent_id, **kwargs):
        if 'address' in self.inputs:
            selection = self.input_view("address").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.address, **kwargs)

        if 'area' in self.inputs:
            selection = self.input_view("area").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.area, **kwargs)

        if 'internet' in self.inputs:
            selection = self.input_view("internet").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.internet, **kwargs)

        if 'parking' in self.inputs:
            selection = self.input_view("parking").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.parking, **kwargs)

        if 'name' in self.inputs:
            kwargs['exclude_words'] = ['hotel']  # do not include these words in the query (reduce db hits)
            selection = self.input_view("name").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.name, **kwargs)
            del kwargs['exclude_words']

        if 'phone' in self.inputs:
            selection = self.input_view("phone").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.phone, **kwargs)

        if 'postcode' in self.inputs:
            selection = self.input_view("postcode").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.postcode, **kwargs)

        if 'pricerange' in self.inputs:
            selection = self.input_view("pricerange").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.pricerange, **kwargs)

        if 'stars' in self.inputs:
            selection = self.input_view("stars").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.stars, **kwargs)

        if 'takesbookings' in self.inputs:
            selection = self.input_view("takesbookings").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.takesbookings, **kwargs)

        if 'type' in self.inputs:
            selection = self.input_view("type").generate_sql_where(
                selection, MultiWozSqlDB.HOTEL_TABLE.columns.type, **kwargs)

        return selection

    def graph_from_row(self, row, context):
        params = []
        for field in self.signature.keys():
            if self.signature[field].custom:
                continue
            value = row[field]
            if value:
                if isinstance(value, str):
                    value = escape_string(value)
                params.append(f"{field}={value}")

        node_str = f"Hotel({', '.join(params)})"
        g, _ = Node.call_construct_eval(node_str, context, constr_tag=NODE_COLOR_DB)
        g.tags[DB_NODE_TAG] = 0
        return g

    def collect_state(self):
        do_collect_state(self, 'hotel')

# use_sep_find_hotel = True  # set to false to use the common Find() logic

def filter_hotel_name_and_set_result(nd, results, filter_name=None):
    if filter_name:
        f, _ = nd.call_construct('Hotel?(name=LIKE(Name(%s)))' % filter_name, nd.context)
        results = [r for r in results if f.match(r)]
    if len(results)==1:
        nd.set_result(results[0])
        results[0].call_eval(add_goal=False)  # not necessary, but adds color
    return results


class HotelBookInfo(Node):
    def __init__(self):
        super().__init__(type(self))
        self.signature.add_sig('bookstay', Book_stay)
        self.signature.add_sig('bookpeople', Book_people)
        self.signature.add_sig('bookday', Book_day)

    def get_context_values(self, inform_values=None, req_fields=None):
        slot_values = {}
        for name in self.inputs:
            element = next(filter(lambda x: x.typename() == "Str", self.input_view(name).topological_order()), None)
            #name = 'book' + name[5:] if name.startswith('book_') else name
            slot_values[f'hotel-{name}'] = [element.dat] if element else []
        if inform_values:
            for k in inform_values:
                slot_values['hotel-'+k] = inform_values[k]

        return slot_values

    def collect_state(self):
        do_collect_state(self, 'hotel', 'book')


class BookHotelConfirmation(Node):
    def __init__(self):
        super().__init__(type(self))
        self.signature.add_sig('hotel', Hotel)
        self.signature.add_sig('book_info', HotelBookInfo)
        self.signature.add_sig('conf_code', Str)

    def describe(self, params=None):
        s = ['Hotel resevation: ']
        m1 = self.input_view('hotel').describe(params=['compact'])
        m2 = self.input_view('book_info').describe()
        s.append(m1.text)
        s.append(m2.text)
        s.append('Confirmation code: ' + self.get_dat('conf_code'))
        return Message('  NL  '.join(s), objects=m1.objects+m2.objects)

    def collect_state(self):
        self.inputs['hotel'].collect_state()
        self.inputs['book_info'].collect_state()
        do_collect_state(self, 'hotel', 'book')  # add conf code directly


def check_hotel_availability(hotel, binf, book_fields):
    if environment_definitions.agent_oracle:
        if 'ref' in book_fields:
            return True, book_fields['ref']
        if 'nobook' in book_fields:
            return False, None
    return True, 'XYZ%12345'  #  % random.randint(1000000, 9000000)


class BookHotel(Node):
    def __init__(self):
        super().__init__(BookHotelConfirmation)
        self.signature.add_sig('hotel', Hotel)
        self.signature.add_sig('book_info', HotelBookInfo)
        # maybe wrap the book info inputs into a node?
        self.inc_count('max_mention_name', 1)

    # todo - add agent_oracle mode!
    def exec(self, all_nodes=None, goals=None):
        #self.update_mwoz_state()

        if 'hotel' not in self.inputs:
            raise MissingValueException('hotel', self, 'Please specify what hotel you are looking for')
        hotel = self.input_view('hotel')
        context = self.context

        # unlike find hotel, there are no recommendations for book hotel (?), so not much to do for oracle
        # maybe: in case of failed booking, then inform what needs to change? todo
        inform_fields = {}
        req_fields = {}
        book_fields = {}
        bfields = ['bookday', 'bookstay', 'bookpeople', 'ref']
        if environment_definitions.agent_oracle:
            dact = context.agent_turn['dialog_act']['dialog_act']
            atext = context.agent_turn['utterance']
            # 1. try to understand what the agent did -
            for d in dact:
                dom, typ = d.split('-')
                if dom=='xxBooking':
                    pass  # todo
                elif dom=='Hotel' or dom=='Booking':
                    if typ == 'Inform':
                        for [k, v] in dact[d]:
                            if k in bfields:
                                inform_fields[k] = v
                    if typ == 'Book':
                        for [k, v] in dact[d]:
                            if k in bfields:
                                book_fields[k] = v
                    if typ == 'NoBook':
                        book_fields['nobook'] = 'True'
                    if typ == 'Request':
                        for [k, v] in dact[d]:
                            if k in bfields:
                                req_fields[k] = v

            if environment_definitions.oracle_only:
                # return the original message of the agent,
                #self.update_mwoz_state(inform_fields, req_fields)
                raise OracleException(atext, self)

        msg = ''
        if self.count_ok('mention_name'):
            self.inc_count('mention_name')
            msg = 'OK, ' + hotel.describe().text + '.  NL  '
        if hotel.inp_equals('takesbookings', 'no'):
            raise InvalidInputException(msg + 'Unfortunately the hotel does not take bookings.   NL  Maybe try another hotel?', self)
        if 'book_info' not in self.inputs:  # should not be the case when using the "normal" initialization (fallback search)
            d, e = self.call_construct('HotelBookInfo()', self.context)
            d.connect_in_out('book_info', self)
        binf = self.inputs['book_info']
        if 'bookstay' not in binf.inputs:
            raise MissingValueException('bookstay', self, msg+'For how many days?')  # todo - add hint - to avoid confusing with num people?
        if 'bookpeople' not in binf.inputs:
            raise MissingValueException('bookpeople', self, msg+'For how many people?')
        if 'bookday' not in binf.inputs:
            raise MissingValueException('bookday', self, msg+'Starting which day?')
        ok, conf_code = check_hotel_availability(hotel, binf, book_fields)
        if ok:
            d, e = self.call_construct_eval('BookHotelConfirmation(hotel=%s, book_info=%s, conf_code=%s)' %
                                            (id_sexp(hotel), id_sexp(binf), conf_code), self.context)
            self.set_result(d)
            self.context.add_message(self, 'I have made the reservation as requested. confirmation ref %s' % conf_code)
        else:
            # todo - if oracle - say what failed / what is needed
            raise InvalidInputException('Unfortunately the hotel can not confirm this booking.    NL  Maybe try another day or length of stay?', self)

    def collect_state(self):
        if self.result != self:
            self.res.collect_state()
        else:
            self.inputs['hotel'].collect_state()
            self.inputs['book_info'].collect_state()

    # even if exception thrown by inputs, we still want to update the state
    # def allows_exception(self, e):
    #     self.update_mwoz_state()
    #     return False, e


# find_hotel can be used in three ways:
#   1. The "normal" way - simply responding to the user's request, using the logic in exec
#   2. Complete oracle - use the agent's text as is
#   3. Mixed oracle - use the agent's dialog acts to guide the logic in exec.
# when using the oracle, we also need to make sure that the RESULT of the node is in line with what the agent said
#   (e.g. if a hotel was mentioned by the agent, bring it to the graph, so we can refer to it)
# when is find_hotel satisfied?
#   in fact, it's only important to clearly say whether it is satisfied or not, if it is going to be used
#      as input to another node. if it's the top node then there is no practical difference between
#      yield message and exception message
# unlike SMCalFlow (e.g. CreateEvent), the agent (oracle) is not a program, but a human, so the response is less
# systematic, as well as often more proactive - e.g. suggesting one option from many, for no clear reason.
# therefore, if using the oracle, we need to detect what did the agent actually do:
#   - describe single/multi results
#   - describe the user request
#   - present multiple options
#   - say there are N options, ask to constrain a field (price/area...)
#   - present a single option (when only one object matches)
#   - select a single option (when many object match)
# (in the absence of an oracle, the logic can "randomly" select one of these options)
# and the logic of exec should then be able to handle these actions (generate result AND message)
# def find_hotel(find, hotel, all_nodes=None, goals=None):
class FindHotel(Node):
    def __init__(self):
        super().__init__(Hotel)
        self.signature.add_sig(posname(1), Hotel, alias='hotel')

    def exec(self, all_nodes=None, goals=None):
        context = self.context
        if posname(1) in self.inputs:
            hotel = self.inputs[posname(1)]
        else:
            hotel, _ = self.call_construct('Hotel?()', context)
            hotel.connect_in_out(posname(1), self)

        results = results0 = multiwoz_db.find_elements_that_match(hotel, hotel.context)
        nresults = nresults0 = len(results)

        # update_mwoz_state(hotel, context)   # initial state from last turn / prev pexp in this turn
        self.filter_and_set_result(results)  # initially set result to single result, if single, or don't

        inform_fields = defaultdict(list)
        rec_field = 'rec_name'
        req_fields = {}
        sugg = None
        objs = None
        if environment_definitions.agent_oracle:
            dact = context.agent_turn['dialog_act']['dialog_act']
            atext = context.agent_turn['utterance']
            # 1. try to understand what the agent did -
            for d in dact:
                dom, typ = d.split('-')
                if dom=='Booking':
                    if typ=='Book':
                        for [k, v] in dact[d]:
                            if k=='name':
                                inform_fields['book_name'].append(v)
                elif dom=='Hotel':
                    if typ in ['Inform', 'Recommend']:
                        for [k, v] in dact[d]:
                            kk = 'rec_' + k if typ == 'Recommend' else k
                            inform_fields[kk].append(v)
                    if typ == 'Request':
                        for [k, v] in dact[d]:
                            req_fields[k] = v

            # for now - if the agent recommends a hotel (by name), then we create a suggestion with implicit accept
            if 'book_name' in inform_fields:
                rec_field = 'book_name'

            if 'name' in inform_fields and len(inform_fields['name'])==1 and nresults0>1 and rec_field not in inform_fields:
                #rec_field = 'name'
                inform_fields['rec_name'] = inform_fields['name']
            if rec_field in inform_fields:
                if len(inform_fields[rec_field])==1:
                    nm = inform_fields[rec_field][0]
                    r = self.filter_and_set_result(results, nm)
                    if r:
                        results = r
                        nresults = len(results)
                    # results should not be empty - unless the agent made a mistake
                    sugg = self.mod_hotel_name_and_suggest_neg(hotel, nm)
                    # objs = add_mention_if_name_match(find, results, nm)  # no need - already added as result
                else:   # ignore multiple recommendations
                    del inform_fields[rec_field]

            if environment_definitions.oracle_only:
                # return the original message of the agent,
                #    but may need to change the result according to the agent's action
                #update_mwoz_state(hotel, context, inform_fields, req_fields)
                raise OracleException(atext, self, suggestions=sugg, objects=objs)

        if not environment_definitions.agent_oracle:  # len(inform_fields)==0:  # no oracle, or oracle didn't say anything - use node logic to select what to report
            # add here logic to recommend a hotel?
            if nresults > 1 and rec_field not in inform_fields:
                dfields = get_diff_fields(results0, ['type', 'parking', 'internet', 'stars', 'pricerange'])
                if len(dfields)>0:
                    for f in list(dfields.keys())[:2]:
                        req_fields[f] = '?'

        if len(inform_fields)>0 or len(req_fields)>0:
            rname = inform_fields.get(rec_field)
            rname = rname[0] if rname else None
            if rname and not sugg:   # the recommendation was added by the logic (didn't come from the agent)
                r = self.filter_and_set_result(results, rname)
                results = r if r else results
                nresults = len(results)
                sugg = self.mod_hotel_name_and_suggest_neg(hotel, rname)
                # objs = add_mention_if_name_match(find, results, rname)  # no need - already added

            # for the selected fields, we now get the ACTUAL values we see in the results
            # in a case like: "all three have free parking. I recommend X" - where there are values as well as
            # a recommendation, we add to the state the values before the recommendation.
            # arbitrary decision. (affects only comparison of states)
            for f in ['name', 'type', 'area', 'stars', 'address', 'phone', 'postcode']:  # todo add more
                if f in inform_fields:
                    inform_fields[f] = collect_values(results0, f)

            if rec_field not in inform_fields or req_fields:  #  and nresults>2:
                if len(req_fields)==0 and not environment_definitions.agent_oracle and nresults>2:  # don't suggest if following oracle
                    dfields = get_diff_fields(results, ['address', 'phone', 'postcode', 'name'])
                    if dfields:
                        req_fields = {i:'?' for i in list(dfields.keys())[:2]}

            msg = self.describe_inform_request(nresults0, inform_fields, req_fields)

            #update_mwoz_state(hotel, context, inform_fields, req_fields)  # use inform_fields to update state
            if nresults!=1 or rec_field in inform_fields:
                raise OracleException(msg, self, suggestions=sugg, objects=objs)
            else:
                self.context.add_message(self, msg)
                return

        # no inform fields and no recommendation
        #update_mwoz_state(hotel, context)  # update without inform fields
        if nresults == 0:
            raise ElementNotFoundException(
                "I can not find a matching hotel in the database. Maybe another area or price range?", self)
        if nresults > 1:
            diffs = ' or '.join(list(inform_fields.keys())[:2])
            if diffs:
                msg = 'Multiple (%d) matches found. Maybe select  %s?' % (nresults, diffs)
            else:
                msg = 'Multiple (%d) matches found. Can you be more specific?' % nresults
            raise MultipleEntriesSingletonException(msg, self, suggestions=sugg, objects=objs)

        # if nresults==1 : success, do nothing

    def fallback_search(self, parent, all_nodes=None, goals=None, do_eval=True, params=None):
        top = [g for g in self.context.goals if g.typename()=='MwozConversation']
        if not top:
            top, _ = self.call_construct('MwozConversation()', self.context)
            self.context.add_goal(top)
        else:
            top = top[-1]
        s = '' if posname(1) in self.inputs else 'Hotel?()'
        d, e = self.call_construct('BookHotel(hotel=FindHotel(%s), book_info=HotelBookInfo())' % s, self.context)
        if posname(1) in self.inputs:
            find = d.inputs['hotel']
            self.inputs[posname(1)].connect_in_out(posname(1), find)
        top.add_task(d)
        h = d.inputs['hotel']
        parent.set_result(h)
        if do_eval:
            e = top.call_eval(add_goal=False)
            if e:
                raise e[0]
        return [h]

    # suggest a hotel by name - unless the user rejects, set the hotel name (implicit agree)
    # def make_hotel_name_suggest(name):
    #     return ['no_op()',
    #             SUGG_IMPL_AGR + 'revise(old=Hotel??(), newMode=overwrite, new=Hotel?(name=LIKE(Name(%s))))' % name]

    # suggest a hotel by name - if user rejects, then clear hotel name
    def mod_hotel_name_and_suggest_neg(self, constr, nm):
        d, e = constr.call_construct('LIKE(Name(%s))' % nm, constr.context)
        constr.replace_input('name', d)
        return ['revise(old=Hotel??(), newMode=overwrite, new=Hotel?(name=Clear()))',
                'side_task(task=no_op())']

    def filter_and_set_result(self, results, filter_name=None):
        if filter_name:
            f, _ = self.call_construct('Hotel?(name=LIKE(Name(%s)))' % filter_name, self.context)
            results = [r for r in results if f.match(r)]
        if len(results)==1:
            self.set_result(results[0])
            results[0].call_eval(add_goal=False)  # not necessary, but adds color
        return results

    def describe_inform_request(self, nresults0, inform_fields, req_fields):
        prms = []
        nm = inform_fields.get('name')
        if nm and 'rec_name' not in inform_fields and 'book_name' not in inform_fields:
            prms.append('I have found ' + and_values_str(nm))

        if 'choice' in inform_fields:
            inform_fields['choice'] = [nresults0]
        choice = inform_fields.get('choice')
        if choice:
            prms.append('There are %d matching results' % nresults0)
        elif nresults0 > 1 and 'book_name' not in inform_fields and 'name' not in inform_fields:
            prms.append('I see several (%d) matches' % nresults0)
        plural=nresults0>1

        typ = inform_fields.get('type')
        if typ:
            prms.append('of type ' + and_values_str(typ))

        area = inform_fields.get('area')
        if area:
            prms.append('In the ' + and_values_str(area))
        prk = inform_fields.get('parking')
        if prk:
            prms.append('There is %sparking%s' % (
            '' if prk[0] == 'yes' else ' ' + prk[0], ' for all of them' if len(prk) == 1 else ''))
        strs = inform_fields.get('stars')
        if strs:
            t = 'They have ' if plural or len(strs)>1 else 'It has '
            prms.append(t + and_values_str(strs) + ' stars')
        adr = inform_fields.get('address')
        if adr:
            adr = adr[0]
            prms.append('It\'s located at ' + adr)
        phone = inform_fields.get('phone')
        if phone:
            prms.append('The phone number is ' + phone[0])
        postcode = inform_fields.get('postcode')
        if postcode:
            prms.append('The post code number is ' + postcode[0])
        price = inform_fields.get('pricerange')
        if price:
            prms.append('The price is ' + price[0])

        if 'rec_name' in inform_fields:
            prms.append('I recommend %s' % inform_fields['rec_name'][0])
        if 'book_name' in inform_fields:
            prms.append('I Have booked %s' % inform_fields['book_name'][0])
        if len(req_fields) > 0:
            if nresults0 > 0:
                prms.append('maybe select %s' % ' or '.join([i for i in req_fields]))
            else:
                prms.append('Sorry, I can\'t find a match. Try a different %s' % ' or '.join([i for i in req_fields]))
        msg = ', '.join(prms)
        return msg

    # if we revise a hotel constraint which already has a hotel name with a non-name constraint, then drop the name.
    #    e.g. user: "I want to book hotel X", Agent: "hotel X is ... and has no parking". User: "I want parking"
    #    also if agent made a suggestion (which was implicitly accepted) - since we don't have explicit RejectSuggestion
    #    we need this implicit reject
    # UNLESS - the old FindHotel already found a specific hotel, and the newly requested value matches the value of the
    #          found hotel (even if that value was not specified by the user in the constraint)
    #          - this can occur e.g. due to annotation error, where a field gets mentioned later than it actually was
    def on_duplicate(self, dup_tree=False):
        super().on_duplicate(dup_tree=dup_tree)
        # old = self.dup_of.input_view('hotel')
        old = self.dup_of.res if self.dup_of.res != self.dup_of else self.dup_of.input_view('hotel')
        curr = self.input_view('hotel')
        if 'name' in old.inputs and 'name' in curr.inputs:
            changed = any([old.get_dat(i)!=curr.get_dat(i) and curr.get_dat(i) is not None
                           for i in ['area', 'stars', 'pricerange', 'internet', 'parking', 'type']])
            if changed:
                curr.disconnect_input('name')
        return self

    def collect_state(self):
        if self.result!=self:
            self.res.collect_state()
        elif 'hotel' in self.inputs:
            self.inputs['hotel'].collect_state()


# demonstrating the idea of simplification/expansion -
# deprecated
# class revise_hotel(revise):
#     def __init__(self):
#         super().__init__()
#
#     def transform_graph(self, top):
#         pnm, parent = self.get_parent()
#         prms = ['%s=%s' % (i, id_sexp(self.input_view(i))) for i in self.inputs if i in self.inputs]
#         s = 'revise(old=Hotel??(), new=Hotel?(%s), newMode=overwrite)' % ','.join(prms)
#         d, e = self.call_construct(s, self.context)
#         self.replace_self(d)
#         return parent, None


# another version
# this revise_hotel should replace calls to raise_task, revise(Hotel??) and revise(HotelBookInfo)
# this node performs these tasks itself, rather than being transformed into a combination of other nodes.
class revise_hotel(revise):
    # make it a subtype of revise, so we don't revise this call
    def __init__(self):
        super().__init__()
        # for the hotel
        self.signature.add_sig('area', Area)
        self.signature.add_sig('internet', Internet)
        self.signature.add_sig('parking', Parking)
        self.signature.add_sig('name', Name)
        self.signature.add_sig('pricerange', Pricerange)
        self.signature.add_sig('stars', Stars)
        self.signature.add_sig('type', Type)
        # for the hotel, but unlikely that the user will directly try to change these - maybe remove these
        self.signature.add_sig('address', Address)
        self.signature.add_sig('phone', Phone)
        self.signature.add_sig('postcode', Postcode)
        self.signature.add_sig('takesbookings', Takesbookings)
        # for booking
        self.signature.add_sig('bookstay', Book_stay)
        self.signature.add_sig('bookpeople', Book_people)
        self.signature.add_sig('bookday', Book_day)

    def valid_input(self):  # override the revise valid_input
        pass

    def transform_graph(self, top):
        if 'name' in self.inputs:
            n = self.input_view('name')
            if n.typename()=='Name':
                self.wrap_input('name', 'LIKE(')
        return self, None

    def exec(self, all_nodes=None, goals=None):
        # 1. raise or create task
        root = do_raise_task(self, 'FindHotel') #  the top conversation

        # 2. do revise if requested fields given
        hotel_fields = ['area', 'internet', 'parking', 'name', 'pricerange', 'stars', 'type',
                        'address', 'phone', 'postcode',  'takesbookings']
        book_fields = ['bookstay', 'bookpeople', 'bookday']
        fields = {'hotel': [i for i in self.inputs if i in hotel_fields],
                  'book': [i for i in self.inputs if i in book_fields]}
        for f in fields:
            if fields[f]:
                nodes = root.topological_order(follow_res=False)
                book = [i for i in nodes if i.typename()=='BookHotel']
                if book:  # should always be the case
                    book = book[0]
                    prms = ['%s=%s' % (i, id_sexp(self.inputs[i])) for i in fields[f]]
                    # we know exactly what root/old/new should be, so no need to use the search mechanism of the
                    #   'revise' node - instead we can directly call duplicate_subgraph to create the revised graph
                    if f=='hotel':
                        old = book.inputs['hotel'].inputs['hotel']
                        s = 'Hotel?(' + ','.join(prms) + ')'
                    else:  # book info
                        old = book.inputs['book_info']
                        s = 'HotelBookInfo(' + ','.join(prms) + ')'
                    new, _ = self.call_construct(s, self.context)
                    new_subgraph = duplicate_subgraph(root, old, new, 'overwrite', self)
                    root = new_subgraph[-1]

        self.set_result(root)
        self.context.add_goal(root)  # will not add if already added before
        # root.call_eval()  # no need to call eval, since eval_res is True. is this what we want?


# use this node is for debugging - replace the "proactive" hotel recommendation by the agent
# implement recommendation as a suggestion with implicit accept
class suggest_hotel(Node):
    def __init__(self):
        super().__init__()
        self.signature.add_sig(posname(1), Str)

    def exec(self, all_nodes=None, goals=None):
        if posname(1) in self.inputs:
            nm = self.get_dat(posname(1))
            suggs = ['no_op()',
                     SUGG_IMPL_AGR + 'revise(old=Hotel??(), newMode=overwrite, new=Hotel?(name=LIKE(Name(%s))))' % nm]
            raise OracleException('How about %s?' % nm, self, suggestions=suggs)
        # optionally - if no name given, try to get one from the available possible hotels


class get_hotel_info(Node):
    def __init__(self):
        super().__init__()
        self.signature.add_sig('hotel', Hotel)
        # self.signature.add_sig('feats', Node)
        self.signature.add_sig(POS, Str)

    def transform_graph(self, top):
        pnm, parent = self.get_parent()
        if parent.typename()!='side_task':
            if PERSIST_SIDE:
                parent.wrap_input(pnm, 'side_task(persist=True,task=', do_eval=False)
            else:
                parent.wrap_input(pnm, 'side_task(task=', do_eval=False)
            return parent, None
        return self, None

    def exec(self, all_nodes=None, goals=None):
        hotel = self.input_view('hotel')
        if not hotel:
            m = get_refer_match(self.context, all_nodes, goals, type='Hotel')
            if m:
                hotel = m[0]
            else:
                raise MissingValueException('hotel', self, 'I can give information only after we have selected one hotel')
        if hotel:
            fts = []
            fts += [self.input_view(i).dat for i in self.inputs if is_pos(i)]
            if fts:
                vals = ['the %s is %s' %(i, hotel.get_dat(i)) for i in fts]
                msg = 'For %s: ' % hotel.get_dat('name') + ',  NL  '.join(vals)
                self.context.add_message(self, msg)

    def yield_msg(self, params=None):
        msg = self.context.get_node_messages(self)
        return msg[0] if msg else Message('')
        # msg = [m for (n,m) in self.context.messages if n==self]
        # return (msg[0], []) if msg else ('', [])
        # how to deal with missing hotel?  - for now just assume the message was attached to the node already


################################################################################################################


# TODO: how do we treat multiple possible values? Check if any is in the input?
#  Check if we can find any by refer?
def extract_find_hotel(utterance, slots, context, general=None):
    extracted = []
    extracted_book = []
    problems = set()
    has_req = any([i for i in slots if 'request' in i])
    for name, value in slots.items():
        if 'choice' in name:
            continue
        value = select_value(value)
        if not name.startswith(HOTEL_PREFIX) or 'request' in name:
            if 'request' not in name:
                problems.add(f"Slot {name} not mapped for find_hotel!")
            continue
        role = name[HOTEL_PREFIX_LENGTH:]
        if value in SPECIAL_VALUES:
            if role in {'bookstay', 'bookpeople', 'bookday'}:
                extracted_book.append(f"{role}={SPECIAL_VALUES[value]}")
            else:
                extracted.append(f"{role}={SPECIAL_VALUES[value]}")
            continue

        if context and value not in utterance:
            references = get_refer_match(context, Node.collect_nodes(context.goals), context.goals,
                                         role=role, params={'fallback_type':'SearchCompleted', 'role': role})
            if references and references[0].dat == value:
                if role in {'bookstay', 'bookpeople', 'bookday'}:
                    extracted_book.append(f"{role}=refer(role={role})")
                else:
                    extracted.append(f"{role}=refer(role={role})")
                continue
            # else:
            # TODO: maybe log that the reference could not be found in the graph

        if name == "hotel-name":
            if EXTRACT_SIMP:
                extracted.append(f"name={escape_string(value)}")
            else:
                extracted.append(f"name=LIKE(Name({escape_string(value)}))")
        elif name == "hotel-stars":
            extracted.append(f"stars={escape_string(value)}")
        elif name == "hotel-internet":
            extracted.append(f"internet={escape_string(value)}")
        elif name == "hotel-pricerange":
            extracted.append(f"pricerange={escape_string(value)}")
        elif name == "hotel-type":
            extracted.append(f"type={escape_string(value)}")
        elif name == "hotel-parking":
            extracted.append(f"parking={escape_string(value)}")
        elif name == "hotel-area":
            extracted.append(f"area={escape_string(value)}")

        elif name == "hotel-bookstay":
            extracted_book.append(f"bookstay={escape_string(value)}")
        elif name == "hotel-bookpeople":
            extracted_book.append(f"bookpeople={escape_string(value)}")
        elif name == "hotel-bookday":
            extracted_book.append(f"bookday={escape_string(value)}")
        else:
            problems.add(f"Slot {name} not mapped for find_hotel!")

    extracted_req = []
    if has_req:
        for name, value in slots.items():
            if 'request' in name:
                value = select_value(value)
                if not name.startswith(HOTEL_PREFIX + 'request-'):
                    problems.add(f"Slot {name} not mapped for find_hotel request!")
                    continue

                role = name[HOTEL_PREFIX_LENGTH+len('request-'):]
                if role in ['name', 'stars', 'internet', 'pricerange', 'type', 'parking', 'area', 'address', 'phone']:
                    #if not any([role+'=' in i for i in extracted]):
                    extracted_req.append(role)
                # todo - add other fields and check not a bad field name

    exps = get_extract_exps('Hotel', context, general, extracted, extracted_book, extracted_req)

    return exps, problems
