// Copyright (c) 2018 HarryR
// License: LGPL-3.0+


#include "gadgets/longsightl.hpp"
#include "stubs.hpp"

namespace ethsnarks {

bool test_LongsightL()
{
    std::vector<FieldT> round_constants;
    LongsightL12p5_constants_fill(round_constants);

    ProtoboardT pb;

    VariableT m_0;
    VariableT m_1;
    VariableT iv;

    m_0.allocate(pb);
    pb.val(m_0) = FieldT("3703141493535563179657531719960160174296085208671919316200479060314459804651");

    m_1.allocate(pb);
    pb.val(m_1) = FieldT("134551314051432487569247388144051420116740427803855572138106146683954151557");

    pb.set_input_sizes(2);

    iv.allocate(pb);
    pb.val(iv) = FieldT("918403109389145570117360101535982733651217667914747213867238065296420114726");

    LongsightL12p5_MP_gadget the_gadget(pb, iv, {m_0, m_1});
    the_gadget.generate_r1cs_witness();
    the_gadget.generate_r1cs_constraints();


    auto result_expected = FieldT("16743249391414211194903251836323254089433285237756741022465555151301952011503");
    if( result_expected != pb.val(the_gadget.result()) ) {
        std::cerr << "Unexpected result!\n";
        return false;
    }

    std::cout << pb.num_constraints() << " constraints" << std::endl;

    if( ! pb.is_satisfied() ) {
        std::cerr << "Not satisfied!" << std::endl;
        return false;
    }

    return stub_test_proof_verify(pb);
}

// namespace ethsnarks
}


int main( int argc, char **argv )
{
    // Types for board
    ethsnarks::ppT::init_public_params();

    if( ! ethsnarks::test_LongsightL() )
    {
        std::cerr << "FAIL\n";
        return 1;
    }

    std::cout << "OK\n";
    return 0;
}
